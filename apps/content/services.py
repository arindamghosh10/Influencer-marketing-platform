"""Content workflow: draft → brand review → creator final approval → publish → verify → payout.

Slot status moves:
  CONFIRMED → IN_REVIEW ⇄ CHANGES_REQUESTED (max 2 change rounds) → APPROVED
  → SCHEDULED (auto-publish) or SELF_POST (creator posts) → LIVE → VERIFIED (payout released)
  LIVE → ON_HOLD if the post disappears or loses its ad disclosure; back to LIVE if restored.

Timed steps (brand review timeout, scheduled publishing, verification checks) are driven by
`run_due(now)`, called from the scheduled jobs every few minutes.
"""

import hashlib
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.contracts.models import ConsentEvent, ConsentScope
from apps.contracts.services import has_consent
from apps.core.events import client_ip, notify, record
from apps.integrations.instagram.base import InstagramError, InstagramToken
from apps.integrations.llm.rules import RISKY_CLAIM_PATTERNS
from apps.integrations.registry import get_provider
from apps.offers.models import Slot

from .models import Asset, MetricSnapshot, Post, Review

log = logging.getLogger(__name__)

DISCLOSURE_RE = re.compile(r"(#ad\b|#sponsored\b|#paidpartnership\b|paid partnership)", re.I)
VIDEO_TYPES = {"video/mp4", "video/quicktime"}
IMAGE_TYPES = {"image/jpeg", "image/png"}
MAX_CAPTION = 2200  # Instagram limit
MAX_HASHTAGS = 30  # Instagram limit
PUBLISH_MAX_ATTEMPTS = 3
PUBLIC_URL_MAX_AGE = 2 * 24 * 3600
SIGNING_SALT = "content.public-asset"


class ContentError(Exception):
    pass


# --- Automated checks -------------------------------------------------------------------


def _phrases(text):
    return [p.strip() for p in re.split(r"[,\n;]", text or "") if len(p.strip()) > 2]


def run_checks(slot, caption, content_type, size):
    """[{level: block|warn|pass, message}] for a draft. Any 'block' stops the submission."""
    campaign = slot.campaign
    checks = []

    def add(level, message):
        checks.append({"level": level, "message": message})

    wants_video = campaign.deliverable in ("reel", "story")
    allowed = VIDEO_TYPES | (IMAGE_TYPES if campaign.deliverable != "reel" else set())
    if content_type not in allowed:
        kind = "an MP4/MOV video" if wants_video and campaign.deliverable == "reel" else "a video or image"
        add("block", f"Upload {kind} for a {campaign.get_deliverable_display()}.")
    if size > settings.MAX_UPLOAD_MB * 1024 * 1024:
        add("block", f"File is larger than {settings.MAX_UPLOAD_MB} MB.")

    if DISCLOSURE_RE.search(caption):
        add("pass", "Paid-partnership disclosure is in the caption.")
    else:
        add(
            "block",
            "Add a disclosure to the caption, e.g. '#ad' or 'Paid partnership with <brand>' (ASCI rules).",
        )
    if len(caption) > MAX_CAPTION:
        add("block", f"Caption is longer than Instagram's {MAX_CAPTION} characters.")
    if caption.count("#") > MAX_HASHTAGS:
        add("block", f"Instagram allows at most {MAX_HASHTAGS} hashtags.")

    lowered = caption.lower()
    for phrase in _phrases(campaign.must_not_say):
        if phrase.lower() in lowered:
            add("block", f"Caption mentions '{phrase}', which the brand asked you not to say.")
    for pattern in RISKY_CLAIM_PATTERNS:
        match = re.search(pattern, caption, re.I)
        if match:
            add(
                "warn",
                f"'{match.group(0)}' is a claim that needs proof under ASCI rules. "
                "Remove it unless the brand confirms.",
            )
    missing = [p for p in _phrases(campaign.must_say) if p.lower() not in lowered]
    if missing:
        add("warn", "The brand asked you to mention: " + ", ".join(missing) + " (in the video or caption).")
    return checks


def blocking(checks):
    return [c["message"] for c in checks if c["level"] == "block"]


# --- Creator brief ------------------------------------------------------------------------


def ensure_creator_brief(slot):
    """Hooks, script outline, shot list and caption suggestion for this creator (cached)."""
    if slot.creator_brief:
        return slot.creator_brief
    from apps.integrations.llm.rules import RulesLLM

    brief = slot.campaign.confirmed_brief
    data = brief.data if brief else {}
    try:
        provider = get_provider("llm")
        result = provider.creator_brief(data, slot.campaign, slot.creator)
    except Exception as exc:  # any AI failure (quota, network, bad output) falls back to the template
        log.warning("Creator brief via LLM failed, using template: %s", exc)
        result = RulesLLM().creator_brief(data, slot.campaign, slot.creator)
    slot.creator_brief = result.model_dump()
    slot.save(update_fields=["creator_brief", "updated_at"])
    return slot.creator_brief


# --- Drafts and reviews -------------------------------------------------------------------


def _sha256(uploaded):
    digest = hashlib.sha256()
    for chunk in uploaded.chunks():
        digest.update(chunk)
    uploaded.seek(0)
    return digest.hexdigest()


@transaction.atomic
def submit_draft(slot, user, uploaded, caption):
    slot = Slot.objects.select_for_update().get(pk=slot.pk)
    if slot.status not in (Slot.Status.CONFIRMED, Slot.Status.CHANGES_REQUESTED):
        raise ContentError("You can't upload a new draft at this stage.")
    content_type = (uploaded.content_type or "").split(";")[0].lower()
    checks = run_checks(slot, caption, content_type, uploaded.size)
    problems = blocking(checks)
    if problems:
        raise ContentError(" ".join(problems))
    last = slot.assets.order_by("-version").first()
    slot.assets.filter(status__in=[Asset.Status.IN_REVIEW, Asset.Status.CHANGES_REQUESTED]).update(
        status=Asset.Status.SUPERSEDED
    )
    asset = Asset.objects.create(
        slot=slot,
        version=(last.version + 1) if last else 1,
        file=uploaded,
        original_name=uploaded.name[:255],
        content_type=content_type,
        size=uploaded.size,
        sha256=_sha256(uploaded),
        caption=caption,
        checks=checks,
        uploaded_by=user,
    )
    slot.status = Slot.Status.IN_REVIEW
    slot.review_due_at = timezone.now() + timedelta(hours=settings.BRAND_REVIEW_HOURS)
    slot.save(update_fields=["status", "review_due_at", "updated_at"])
    campaign = slot.campaign
    record(
        "content.submitted",
        f"{slot.creator.display_name} submitted draft v{asset.version}",
        actor=user,
        target=campaign,
        data={"sha256": asset.sha256},
    )
    notify(
        campaign.brand.user,
        f"New draft from {slot.creator.display_name}",
        f"Please review within {settings.BRAND_REVIEW_HOURS} hours; after that it's approved automatically.",
        url=reverse("content:review", args=[campaign.pk, slot.pk]),
    )
    return asset


def latest_asset(slot):
    return slot.assets.exclude(status=Asset.Status.SUPERSEDED).order_by("-version").first()


def _approve(slot, asset, reviewer, decision, comment=""):
    Review.objects.create(asset=asset, reviewer=reviewer, decision=decision, comment=comment)
    asset.status = Asset.Status.APPROVED
    asset.save(update_fields=["status"])
    slot.status = Slot.Status.APPROVED
    slot.review_due_at = None
    slot.save(update_fields=["status", "review_due_at", "updated_at"])
    record(
        "content.approved",
        f"Draft v{asset.version} approved ({Review.Decision(decision).label})",
        actor=reviewer,
        target=slot.campaign,
    )
    notify(
        slot.creator.user,
        f"{slot.campaign.brand.company_name} approved your draft 🎉",
        "Give your final OK and choose when it goes live.",
        url=reverse("content:workspace", args=[slot.pk]),
    )


@transaction.atomic
def brand_review(slot, asset, reviewer, decision, comment=""):
    slot = Slot.objects.select_for_update().get(pk=slot.pk)
    asset = Asset.objects.select_for_update().get(pk=asset.pk)
    if slot.status != Slot.Status.IN_REVIEW or asset.status != Asset.Status.IN_REVIEW:
        raise ContentError("This draft isn't waiting for review.")
    if decision == Review.Decision.APPROVED:
        _approve(slot, asset, reviewer, decision, comment)
        return
    if slot.revisions_used >= settings.MAX_REVISIONS:
        raise ContentError(
            f"You've used all {settings.MAX_REVISIONS} revision rounds. Approve this version, or contact "
            "support if it doesn't follow the brief."
        )
    if not comment.strip():
        raise ContentError("Tell the creator what to change.")
    Review.objects.create(asset=asset, reviewer=reviewer, decision=Review.Decision.CHANGES, comment=comment)
    asset.status = Asset.Status.CHANGES_REQUESTED
    asset.save(update_fields=["status"])
    slot.status = Slot.Status.CHANGES_REQUESTED
    slot.revisions_used += 1
    slot.review_due_at = None
    slot.save(update_fields=["status", "revisions_used", "review_due_at", "updated_at"])
    record(
        "content.changes_requested",
        f"Changes requested on v{asset.version} (round {slot.revisions_used} of {settings.MAX_REVISIONS})",
        actor=reviewer,
        target=slot.campaign,
    )
    notify(
        slot.creator.user,
        f"{slot.campaign.brand.company_name} asked for changes",
        comment[:300],
        url=reverse("content:workspace", args=[slot.pk]),
    )


def auto_approve_overdue(now):
    count = 0
    for slot_id in Slot.objects.filter(status=Slot.Status.IN_REVIEW, review_due_at__lt=now).values_list(
        "pk", flat=True
    ):
        with transaction.atomic():
            slot = Slot.objects.select_for_update().get(pk=slot_id)
            asset = latest_asset(slot)
            if (
                slot.status != Slot.Status.IN_REVIEW
                or asset is None
                or asset.status != Asset.Status.IN_REVIEW
            ):
                continue
            _approve(slot, asset, None, Review.Decision.AUTO_APPROVED)
            notify(
                slot.campaign.brand.user,
                f"Draft from {slot.creator.display_name} was auto-approved",
                f"It wasn't reviewed within {settings.BRAND_REVIEW_HOURS} hours, as agreed in your order.",
                url=reverse("content:review", args=[slot.campaign_id, slot.pk]),
            )
            count += 1
    return count


# --- Final approval and publishing --------------------------------------------------------


def creator_token(creator):
    return InstagramToken(creator.ig_access_token or "", creator.ig_user_id, creator.ig_token_expires_at)


def can_auto_publish(creator):
    return bool(creator.ig_access_token) and has_consent(creator.user, ConsentScope.INSTAGRAM_PUBLISH)


@transaction.atomic
def final_approve(slot, request, publish_at, auto_publish):
    """The creator's explicit OK for this exact file and caption. Nothing publishes without it."""
    slot = Slot.objects.select_for_update().get(pk=slot.pk)
    asset = latest_asset(slot)
    if slot.status != Slot.Status.APPROVED or asset is None or asset.status != Asset.Status.APPROVED:
        raise ContentError("There's no approved draft waiting for your final OK.")
    now = timezone.now()
    if publish_at < now - timedelta(minutes=5) or publish_at > now + timedelta(days=30):
        raise ContentError("Choose a time between now and 30 days from now.")
    creator = slot.creator
    use_api = auto_publish and can_auto_publish(creator)
    asset.status = Asset.Status.FINAL
    asset.save(update_fields=["status"])
    ConsentEvent.objects.create(
        user=request.user,
        scope=ConsentScope.INSTAGRAM_PUBLISH if use_api else ConsentScope.TERMS,
        action=ConsentEvent.Action.GRANTED,
        campaign=slot.campaign,
        asset_sha256=asset.sha256,
        ip_address=client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:400],
    )
    post = Post.objects.create(
        slot=slot,
        asset=asset,
        method=Post.Method.API if use_api else Post.Method.SELF,
        status=Post.Status.SCHEDULED if use_api else Post.Status.AWAITING_SELF_POST,
        scheduled_for=max(publish_at, now),
    )
    slot.status = Slot.Status.SCHEDULED if use_api else Slot.Status.SELF_POST
    slot.save(update_fields=["status", "updated_at"])
    record(
        "content.final_approved",
        f"{creator.display_name} gave final approval for v{asset.version} "
        f"({'auto-publish' if use_api else 'self-post'} at {post.scheduled_for:%d %b %H:%M})",
        actor=request.user,
        target=slot.campaign,
        data={"sha256": asset.sha256},
        request=request,
    )
    return post


def public_asset_url(asset):
    token = signing.dumps(asset.pk, salt=SIGNING_SALT)
    return settings.SITE_URL.rstrip("/") + reverse("content:public_asset", args=[token])


def asset_from_public_token(token):
    pk = signing.loads(token, salt=SIGNING_SALT, max_age=PUBLIC_URL_MAX_AGE)
    return Asset.objects.get(pk=pk)


def publish_post(post):
    slot = post.slot
    creator = slot.creator
    provider = get_provider("instagram")
    post.publish_attempts += 1
    try:
        media = provider.publish(
            creator_token(creator),
            public_asset_url(post.asset),
            post.asset.caption,
            slot.campaign.deliverable,
        )
    except InstagramError as exc:
        post.last_error = str(exc)[:500]
        if post.publish_attempts >= PUBLISH_MAX_ATTEMPTS:
            _switch_to_self_post(post)
        else:
            post.scheduled_for = timezone.now() + timedelta(minutes=15 * post.publish_attempts)
            post.save(update_fields=["publish_attempts", "last_error", "scheduled_for", "updated_at"])
        return False
    post.save(update_fields=["publish_attempts", "updated_at"])
    mark_live(post, media.media_id, media.permalink)
    return True


def _switch_to_self_post(post):
    post.method = Post.Method.SELF
    post.status = Post.Status.AWAITING_SELF_POST
    post.save()
    slot = post.slot
    slot.status = Slot.Status.SELF_POST
    slot.save(update_fields=["status", "updated_at"])
    record(
        "post.self_post_fallback", f"Auto-publishing failed: {post.last_error[:200]}", target=slot.campaign
    )
    notify(
        slot.creator.user,
        "Please post your approved content yourself",
        "We couldn't publish automatically. Download the approved file, post it with the approved caption "
        "(add the paid-partnership label), then paste the link.",
        url=reverse("content:workspace", args=[slot.pk]),
    )


@transaction.atomic
def submit_self_post(slot, permalink):
    slot = Slot.objects.select_for_update().get(pk=slot.pk)
    post = slot.post
    if post.status != Post.Status.AWAITING_SELF_POST:
        raise ContentError("This post isn't waiting for a link.")
    media = get_provider("instagram").find_media_by_permalink(creator_token(slot.creator), permalink)
    if media is None:
        raise ContentError("We couldn't find that post on your connected Instagram account. Check the link.")
    if Post.objects.filter(ig_media_id=media.media_id).exclude(pk=post.pk).exists():
        raise ContentError("That post is already linked to another campaign.")
    mark_live(post, media.media_id, media.permalink or permalink)


def mark_live(post, media_id, permalink):
    now = timezone.now()
    post.ig_media_id = media_id
    post.permalink = permalink
    post.published_at = now
    post.status = Post.Status.LIVE
    post.next_check_at = now + timedelta(days=1)
    post.monitoring_ends_at = now + timedelta(days=settings.MIN_LIVE_DAYS)
    post.save()
    slot = post.slot
    slot.status = Slot.Status.LIVE
    slot.save(update_fields=["status", "updated_at"])
    record(
        "post.live",
        f"{slot.creator.display_name}'s post is live",
        target=slot.campaign,
        data={"permalink": permalink},
    )
    notify(
        slot.campaign.brand.user,
        f"{slot.creator.display_name}'s post is live",
        permalink,
        url=reverse("content:review", args=[slot.campaign_id, slot.pk]),
    )
    notify(
        slot.creator.user,
        "Your post is live 🎉",
        f"Keep it up (with the disclosure) for {settings.VERIFICATION_DAYS} days "
        "and your payout is released.",
        url=reverse("content:workspace", args=[slot.pk]),
    )
    _snapshot(post)


# --- Verification ---------------------------------------------------------------------------


def _snapshot(post):
    try:
        status = get_provider("instagram").media_status(creator_token(post.slot.creator), post.ig_media_id)
    except InstagramError as exc:
        log.warning("Metrics fetch failed for post %s: %s", post.pk, exc)
        return None
    if status.exists:
        MetricSnapshot.objects.create(
            post=post,
            reach=status.reach,
            views=status.views,
            likes=status.likes,
            comments=status.comments,
            shares=status.shares,
            saves=status.saves,
        )
    return status


def check_post(post, now):
    """One verification check. Returns the new post status."""
    status = _snapshot(post)
    post.last_checked_at = now
    if status is None:  # API error: try again in an hour, don't penalise the creator
        post.next_check_at = now + timedelta(hours=1)
        post.save(update_fields=["last_checked_at", "next_check_at", "updated_at"])
        return post.status
    slot = post.slot
    problem = None
    if not status.exists:
        problem = "The post can't be found (deleted, archived or made private)."
    elif status.caption is not None and not DISCLOSURE_RE.search(status.caption):
        problem = "The paid-partnership disclosure was removed from the caption."

    if problem:
        _handle_problem(post, slot, problem, now)
    else:
        if post.status == Post.Status.MISSING:
            post.status = Post.Status.VERIFIED if post.verified_at else Post.Status.LIVE
            post.missing_since = None
            if slot.status == Slot.Status.ON_HOLD:
                slot.status = Slot.Status.LIVE
                slot.save(update_fields=["status", "updated_at"])
            record("post.restored", f"{slot.creator.display_name}'s post is back", target=slot.campaign)
        if post.status == Post.Status.LIVE and now >= post.published_at + timedelta(
            days=settings.VERIFICATION_DAYS
        ):
            _verify(post, slot, now)
    # Daily checks until verified, then weekly until the minimum live period ends.
    if post.status in (Post.Status.LIVE, Post.Status.MISSING):
        post.next_check_at = now + timedelta(days=1)
    elif post.monitoring_ends_at and now < post.monitoring_ends_at:
        post.next_check_at = min(now + timedelta(days=7), post.monitoring_ends_at)
    else:
        post.next_check_at = None
    post.save()
    return post.status


def _handle_problem(post, slot, problem, now):
    first_time = post.status != Post.Status.MISSING
    after_payout = post.verified_at is not None
    post.status = Post.Status.MISSING
    post.missing_since = post.missing_since or now
    if not after_payout and slot.status == Slot.Status.LIVE:
        slot.status = Slot.Status.ON_HOLD
        slot.save(update_fields=["status", "updated_at"])
    if not first_time:
        return
    record("post.missing", f"{slot.creator.display_name}: {problem}", target=slot.campaign)
    notify(
        slot.creator.user,
        "Action needed: your campaign post has a problem",
        f"{problem} Please restore it within 24 hours"
        + (
            ". Your payout is on hold until then."
            if not after_payout
            else ", as agreed in your campaign agreement."
        ),
        url=reverse("content:workspace", args=[slot.pk]),
    )
    notify(
        slot.campaign.brand.user,
        f"Post by {slot.creator.display_name} needs attention",
        problem,
        url=reverse("content:review", args=[slot.campaign_id, slot.pk]),
    )
    from apps.accounts.models import User

    for ops in User.objects.filter(role=User.Role.OPS, is_active=True):
        notify(
            ops,
            f"Post problem on slot {slot.pk}"
            + (" (after payout: consider clawback)" if after_payout else ""),
            problem,
            email=False,
        )


def _verify(post, slot, now):
    from apps.disputes.services import has_open_dispute
    from apps.payments.models import Payout

    post.status = Post.Status.VERIFIED
    post.verified_at = now
    slot.status = Slot.Status.VERIFIED
    slot.save(update_fields=["status", "updated_at"])
    if has_open_dispute(slot):
        # A dispute is open: the post is verified but the payout waits for ops to resolve it.
        record(
            "post.verified",
            f"{slot.creator.display_name}'s post verified; payout on hold (open dispute)",
            target=slot.campaign,
        )
        notify(
            slot.creator.user,
            "Post verified, payout on hold",
            "Your post passed verification. Payment is on hold until the open dispute is resolved.",
            url=reverse("content:workspace", args=[slot.pk]),
        )
        maybe_complete_campaign(slot.campaign)
        return
    Payout.objects.filter(slot=slot, status=Payout.Status.HELD).update(
        status=Payout.Status.RELEASABLE, updated_at=now
    )
    record(
        "post.verified",
        f"{slot.creator.display_name}'s post verified after "
        f"{settings.VERIFICATION_DAYS} days; payout released",
        target=slot.campaign,
    )
    notify(
        slot.creator.user,
        "Payout released 💸",
        "Your post passed verification. The payment reaches your bank within 2 working days.",
        url=reverse("creators:dashboard"),
    )
    maybe_complete_campaign(slot.campaign)


def maybe_complete_campaign(campaign):
    from apps.campaigns.models import Campaign

    statuses = set(campaign.slots.values_list("status", flat=True))
    done = {Slot.Status.VERIFIED, Slot.Status.UNFILLED, Slot.Status.CANCELLED}
    if statuses and statuses <= done and Slot.Status.VERIFIED in statuses:
        campaign.status = Campaign.Status.COMPLETED
        campaign.save(update_fields=["status", "updated_at"])
        record("campaign.completed", "All posts verified: campaign complete", target=campaign)
        notify(
            campaign.brand.user,
            f"'{campaign.title}' is complete",
            "All posts passed verification. See the results on your campaign page.",
            url=reverse("campaigns:detail", args=[campaign.pk]),
        )


def run_due(now=None):
    now = now or timezone.now()
    published = failed = checked = 0
    for post in Post.objects.filter(status=Post.Status.SCHEDULED, scheduled_for__lte=now).select_related(
        "slot__creator", "slot__campaign", "asset"
    ):
        if publish_post(post):
            published += 1
        else:
            failed += 1
    for post in Post.objects.filter(
        status__in=[Post.Status.LIVE, Post.Status.MISSING, Post.Status.VERIFIED], next_check_at__lte=now
    ).select_related("slot__creator__user", "slot__campaign__brand__user"):
        with transaction.atomic():
            check_post(post, now)
        checked += 1
    return {
        "auto_approved": auto_approve_overdue(now),
        "published": published,
        "publish_failures": failed,
        "posts_checked": checked,
    }
