"""Offer workflow.

Every slot moves: OFFERING → ACCEPTED → CONFIRMED (paid). If the creator declines, doesn't
answer in time, or the brand doesn't pay in time, the next backup creator that still fits the
budget is offered the same slot. When no backup is left the slot becomes UNFILLED and the brand
isn't charged for it. Deadlines are stored on rows and processed by `process_deadlines`, which
runs every few minutes, so nothing depends on a timer surviving a restart.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from apps.campaigns.models import Campaign
from apps.campaigns.services import needs_review
from apps.core.events import notify, record
from apps.core.money import format_inr
from apps.creators.models import CreatorProfile
from apps.matching.models import MatchCandidate, MatchRun

from .models import Offer, Slot


class OfferError(Exception):
    pass


def send_blockers(campaign):
    """Why offers can't go out yet (empty list = ready)."""
    problems = []
    if campaign.brand.status != campaign.brand.Status.APPROVED:
        problems.append("Your brand account is still being reviewed. Offers go out once it's approved.")
    brief = campaign.confirmed_brief
    if brief and needs_review(brief) and not campaign.ops_approved_at:
        problems.append("This product is in a sensitive category. Our team is reviewing the campaign.")
    return problems


def committed_amount(campaign, exclude_slot=None):
    """Brand price already promised to creators (pending offers + accepted/paid slots)."""
    slots = campaign.slots.filter(status__in=Slot.COMMITTED)
    pending = Offer.objects.filter(slot__campaign=campaign, status=Offer.Status.PENDING)
    if exclude_slot is not None:
        slots = slots.exclude(pk=exclude_slot.pk)
        pending = pending.exclude(slot=exclude_slot)
    return (slots.aggregate(t=Sum("brand_price"))["t"] or 0) + (
        pending.aggregate(t=Sum("brand_price"))["t"] or 0
    )


def active_load(creator):
    """Campaigns a creator is committed to or has open offers for."""
    return (
        Slot.objects.filter(creator=creator, status__in=[Slot.Status.ACCEPTED, *Slot.IN_PROGRESS]).count()
        + Offer.objects.filter(creator=creator, status=Offer.Status.PENDING).count()
    )


def _make_offer(slot, candidate, actor=None):
    offer = Offer.objects.create(
        slot=slot,
        creator=candidate.creator,
        candidate=candidate,
        creator_fee=candidate.creator_fee,
        brand_price=candidate.brand_price,
        expires_at=timezone.now() + timedelta(hours=settings.OFFER_EXPIRY_HOURS),
    )
    slot.status = Slot.Status.OFFERING
    slot.save(update_fields=["status", "updated_at"])
    campaign = slot.campaign
    notify(
        candidate.creator.user,
        f"New offer: {campaign.brand.company_name} · {format_inr(offer.creator_fee)}",
        f"{campaign.get_deliverable_display()} for '{campaign.title}'. "
        f"Please reply within {settings.OFFER_EXPIRY_HOURS} hours.",
        url=reverse("offers:detail", args=[offer.pk]),
    )
    record(
        "offer.sent",
        f"Offer sent to {candidate.creator.display_name} (slot {slot.position})",
        actor=actor,
        target=campaign,
        data={"offer": offer.pk},
    )
    return offer


@transaction.atomic
def send_offers(campaign, actor):
    campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status != Campaign.Status.SHORTLISTED:
        raise OfferError("Offers have already been sent for this campaign.")
    problems = send_blockers(campaign)
    if problems:
        raise OfferError(problems[0])
    run = campaign.match_runs.first()
    selected = list(run.candidates.filter(selected=True).select_related("creator__user").order_by("rank"))
    if not selected:
        raise OfferError("Select at least one creator first.")
    for position, candidate in enumerate(selected, start=1):
        slot = Slot.objects.create(campaign=campaign, position=position)
        _make_offer(slot, candidate, actor)
    campaign.status = Campaign.Status.OFFERS_OUT
    campaign.save(update_fields=["status", "updated_at"])
    return campaign.slots.all()


TOP_UP_STATUSES = (Campaign.Status.OFFERS_OUT, Campaign.Status.ACTIVE)


@transaction.atomic
def send_top_up(campaign, actor):
    """Send offers to the extra creators picked in a top-up run and add its budget."""
    campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    run = campaign.match_runs.first()
    if run is None or not run.is_pending_top_up:
        raise OfferError("Find more creators first.")
    if campaign.status not in TOP_UP_STATUSES:
        raise OfferError("Creators can only be added while the campaign is running.")
    problems = send_blockers(campaign)
    if problems:
        raise OfferError(problems[0])
    selected = list(run.candidates.filter(selected=True).select_related("creator__user").order_by("rank"))
    if not selected:
        raise OfferError("Select at least one creator first.")
    if sum(c.brand_price for c in selected) > run.budget:
        raise OfferError("Your selection is over the extra budget. Remove a creator or add more budget.")
    taken = Offer.objects.filter(slot__campaign=campaign, creator_id__in=[c.creator_id for c in selected])
    if taken.exists():
        raise OfferError("Some of these creators were already offered this campaign. Find creators again.")
    start = campaign.slots.count()
    slots = []
    for position, candidate in enumerate(selected, start=start + 1):
        slot = Slot.objects.create(campaign=campaign, position=position)
        _make_offer(slot, candidate, actor)
        slots.append(slot)
    campaign.budget += run.budget
    campaign.save(update_fields=["budget", "updated_at"])
    run.sent_at = timezone.now()
    run.save(update_fields=["sent_at"])
    record(
        "campaign.topped_up",
        f"{len(slots)} more creator{'s' if len(slots) != 1 else ''} offered; budget raised by "
        f"{format_inr(run.budget)}",
        actor=actor,
        target=campaign,
    )
    return slots


def backup_run(campaign):
    """Latest match run whose backups may be offered (never an unsent top-up)."""
    return campaign.match_runs.exclude(purpose=MatchRun.Purpose.TOP_UP, sent_at__isnull=True).first()


def next_candidate(slot):
    """Best remaining backup for this slot that still fits the budget and is available."""
    campaign = slot.campaign
    run = backup_run(campaign)
    tried = Offer.objects.filter(slot__campaign=campaign).values_list("creator_id", flat=True)
    headroom = campaign.budget - committed_amount(campaign, exclude_slot=slot)
    # Only the backup list: recommended creators the brand removed are never offered.
    candidates = (
        run.candidates.filter(role=MatchCandidate.Role.BACKUP, selected=False)
        .exclude(creator_id__in=tried)
        .filter(brand_price__lte=headroom)
        .filter(creator__status=CreatorProfile.Status.APPROVED, creator__on_break=False)
        .select_related("creator__user")
        .order_by("rank")
    )
    for candidate in candidates:
        if active_load(candidate.creator) < candidate.creator.max_active_campaigns:
            return candidate
    return None


def _refill(slot, reason):
    """Offer the slot to the next backup, or mark it unfilled."""
    campaign = slot.campaign
    candidate = next_candidate(slot)
    brand_user = campaign.brand.user
    url = reverse("campaigns:detail", args=[campaign.pk])
    if candidate:
        _make_offer(slot, candidate)
        notify(
            brand_user,
            f"{reason}: we've offered the slot to {candidate.creator.display_name}",
            "Your backup creator has been contacted automatically. No action needed.",
            url=url,
        )
    else:
        slot.status = Slot.Status.UNFILLED
        slot.creator = None
        slot.save(update_fields=["status", "creator", "updated_at"])
        record("slot.unfilled", f"Slot {slot.position} couldn't be filled", target=campaign)
        notify(
            brand_user,
            f"{reason}, and no backup is available",
            "You won't be charged for this slot. You can refresh matches later to add another creator.",
            url=url,
        )


def _lock_offer(offer):
    return Offer.objects.select_for_update().select_related("slot__campaign__brand__user").get(pk=offer.pk)


@transaction.atomic
def accept(offer, agreement):
    offer = _lock_offer(offer)
    if offer.status != Offer.Status.PENDING:
        raise OfferError("This offer is no longer open.")
    if offer.expires_at < timezone.now():
        raise OfferError("This offer has expired.")
    now = timezone.now()
    offer.status = Offer.Status.ACCEPTED
    offer.responded_at = now
    offer.agreement = agreement
    offer.save(update_fields=["status", "responded_at", "agreement", "updated_at"])
    slot = offer.slot
    slot.status = Slot.Status.ACCEPTED
    slot.creator = offer.creator
    slot.creator_fee = offer.creator_fee
    slot.brand_price = offer.brand_price
    slot.accepted_at = now
    slot.payment_due_at = now + timedelta(hours=settings.BRAND_PAYMENT_HOURS)
    slot.save()
    campaign = slot.campaign
    record("offer.accepted", f"{offer.creator.display_name} accepted (slot {slot.position})", target=campaign)
    notify(
        campaign.brand.user,
        f"{offer.creator.display_name} accepted your offer",
        "Pay for accepted creators to start production. Creators start as soon as payment is secured.",
        url=reverse("campaigns:detail", args=[campaign.pk]),
    )
    return offer


@transaction.atomic
def decline(offer, reason, note=""):
    offer = _lock_offer(offer)
    if offer.status != Offer.Status.PENDING:
        raise OfferError("This offer is no longer open.")
    offer.status = Offer.Status.DECLINED
    offer.responded_at = timezone.now()
    offer.decline_reason = reason
    offer.decline_note = note[:300]
    offer.save(update_fields=["status", "responded_at", "decline_reason", "decline_note", "updated_at"])
    record(
        "offer.declined",
        f"{offer.creator.display_name} declined ({offer.get_decline_reason_display()})",
        target=offer.slot.campaign,
    )
    _refill(offer.slot, f"{offer.creator.display_name} declined")


@transaction.atomic
def cancel_slot(slot, actor):
    """Brand removes a slot before paying for it."""
    slot = Slot.objects.select_for_update().get(pk=slot.pk)
    if slot.status not in (Slot.Status.OFFERING, Slot.Status.ACCEPTED):
        raise OfferError("Paid or closed slots can't be cancelled here.")
    for offer in slot.offers.filter(status__in=[Offer.Status.PENDING, Offer.Status.ACCEPTED]):
        offer.status = Offer.Status.WITHDRAWN
        offer.save(update_fields=["status", "updated_at"])
        notify(
            offer.creator.user,
            f"Offer withdrawn: {slot.campaign.title}",
            "The brand changed its plans. You haven't been charged anything and are free to take other work.",
        )
    slot.status = Slot.Status.CANCELLED
    slot.save(update_fields=["status", "updated_at"])
    record("slot.cancelled", f"Slot {slot.position} cancelled by brand", actor=actor, target=slot.campaign)


def expire_offers(now=None):
    now = now or timezone.now()
    count = 0
    for offer_id in Offer.objects.filter(status=Offer.Status.PENDING, expires_at__lt=now).values_list(
        "pk", flat=True
    ):
        with transaction.atomic():
            offer = Offer.objects.select_for_update().get(pk=offer_id)
            if offer.status != Offer.Status.PENDING:
                continue
            offer.status = Offer.Status.EXPIRED
            offer.save(update_fields=["status", "updated_at"])
            creator = offer.creator
            # Missing an offer slightly lowers reliability, which affects future matching.
            creator.reliability_score = round(max(0.0, creator.reliability_score - 0.02), 3)
            creator.save(update_fields=["reliability_score", "updated_at"])
            record(
                "offer.expired",
                f"Offer to {creator.display_name} expired without a reply",
                target=offer.slot.campaign,
            )
            _refill(offer.slot, f"{creator.display_name} didn't reply in time")
            count += 1
    return count


def release_unpaid(now=None):
    """Free creators whose brand didn't pay within BRAND_PAYMENT_HOURS of acceptance."""
    from apps.payments.models import Order

    now = now or timezone.now()
    # A checkout that started in the last hour may still be completing; leave it alone.
    in_checkout = Order.objects.filter(
        status=Order.Status.CREATED, created_at__gte=now - timedelta(hours=1)
    ).values_list("pk", flat=True)
    due = Slot.objects.filter(status=Slot.Status.ACCEPTED, payment_due_at__lt=now).exclude(
        order_id__in=list(in_checkout)
    )
    count = 0
    for slot_id in due.values_list("pk", flat=True):
        with transaction.atomic():
            slot = Slot.objects.select_for_update().select_related("campaign__brand__user").get(pk=slot_id)
            if slot.status != Slot.Status.ACCEPTED:
                continue
            offer = slot.offers.filter(status=Offer.Status.ACCEPTED).first()
            if offer:
                offer.status = Offer.Status.RELEASED
                offer.save(update_fields=["status", "updated_at"])
                notify(
                    offer.creator.user,
                    f"Campaign didn't go ahead: {slot.campaign.title}",
                    "The brand didn't confirm payment in time, so you're released from this offer.",
                )
            slot.status = Slot.Status.CANCELLED
            slot.save(update_fields=["status", "updated_at"])
            record("slot.released", f"Slot {slot.position} released: brand didn't pay", target=slot.campaign)
            notify(
                slot.campaign.brand.user,
                "A creator was released because payment wasn't made",
                "Refresh matches to add another creator.",
                url=reverse("campaigns:detail", args=[slot.campaign.pk]),
            )
            count += 1
    return count


def process_deadlines(now=None):
    """Everything time-based: offers, payments, reviews, publishing, verification."""
    from apps.content.services import run_due
    from apps.core.models import JobHeartbeat
    from apps.creators.sync import sync_due

    from .reminders import send_reminders

    now = now or timezone.now()
    result = {"expired_offers": expire_offers(now), "released_slots": release_unpaid(now)}
    result.update(run_due(now))
    result.update(sync_due(now))
    result["reminders"] = send_reminders(now)
    JobHeartbeat.objects.update_or_create(
        name="process_deadlines", defaults={"last_run_at": timezone.now(), "last_result": result}
    )
    return result
