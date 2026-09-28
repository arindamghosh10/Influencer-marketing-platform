from django.contrib import messages
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.brands.views import get_brand
from apps.core.permissions import brand_required, creator_required
from apps.offers.models import Slot

from . import services
from .forms import DraftForm, FinalApprovalForm, ReviewForm, SelfPostForm
from .models import Asset

# --- Creator -------------------------------------------------------------------------------


def _creator_slot(request, slot_id):
    return get_object_or_404(
        Slot.objects.select_related("campaign__brand", "creator"),
        pk=slot_id,
        creator__user=request.user,
        status__in=[*Slot.IN_PROGRESS, Slot.Status.VERIFIED],
    )


def _post_context(slot):
    post = getattr(slot, "post", None)
    latest = post.snapshots.first() if post else None
    return {"post": post, "metrics": latest, "verification_days": services.settings.VERIFICATION_DAYS}


@creator_required
def workspace(request, slot_id):
    slot = _creator_slot(request, slot_id)
    campaign = slot.campaign
    brief = campaign.confirmed_brief
    context = {
        "slot": slot,
        "campaign": campaign,
        "brief": brief.data if brief else {},
        "creator_brief": services.ensure_creator_brief(slot),
        "assets": slot.assets.prefetch_related("reviews"),
        "latest": services.latest_asset(slot),
        "draft_form": DraftForm(),
        "final_form": FinalApprovalForm(),
        "self_post_form": SelfPostForm(),
        "can_auto_publish": services.can_auto_publish(slot.creator),
        "max_revisions": services.settings.MAX_REVISIONS,
        **_post_context(slot),
    }
    return render(request, "content/workspace.html", context)


@creator_required
@require_POST
def submit_draft(request, slot_id):
    slot = _creator_slot(request, slot_id)
    form = DraftForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Please add a file and a caption.")
        return redirect("content:workspace", slot_id=slot.pk)
    try:
        services.submit_draft(slot, request.user, form.cleaned_data["file"], form.cleaned_data["caption"])
        messages.success(request, "Draft sent to the brand. We'll let you know when they reply.")
    except services.ContentError as exc:
        messages.error(request, str(exc))
    return redirect("content:workspace", slot_id=slot.pk)


@creator_required
@require_POST
def final_approve(request, slot_id):
    slot = _creator_slot(request, slot_id)
    form = FinalApprovalForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please choose a time and tick the approval box.")
        return redirect("content:workspace", slot_id=slot.pk)
    publish_at = form.cleaned_data["publish_at"]
    if timezone.is_naive(publish_at):
        publish_at = timezone.make_aware(publish_at)
    try:
        post = services.final_approve(slot, request, publish_at, form.cleaned_data["auto_publish"])
    except services.ContentError as exc:
        messages.error(request, str(exc))
        return redirect("content:workspace", slot_id=slot.pk)
    if post.method == post.Method.API:
        messages.success(
            request, f"Approved. It goes live on {timezone.localtime(post.scheduled_for):%d %b at %H:%M}."
        )
    else:
        messages.success(request, "Approved. Post it at your chosen time, then paste the link here.")
    return redirect("content:workspace", slot_id=slot.pk)


@creator_required
@require_POST
def self_post(request, slot_id):
    slot = _creator_slot(request, slot_id)
    form = SelfPostForm(request.POST)
    if not form.is_valid():
        messages.error(request, form.errors["permalink"][0])
        return redirect("content:workspace", slot_id=slot.pk)
    try:
        services.submit_self_post(slot, form.cleaned_data["permalink"])
        messages.success(request, "Got it: your post is live and verification has started.")
    except services.ContentError as exc:
        messages.error(request, str(exc))
    return redirect("content:workspace", slot_id=slot.pk)


# --- Brand ---------------------------------------------------------------------------------


def _brand_slot(request, campaign_id, slot_id):
    return get_object_or_404(
        Slot.objects.select_related("campaign__brand", "creator"),
        pk=slot_id,
        campaign_id=campaign_id,
        campaign__brand=get_brand(request),
    )


@brand_required
def review(request, campaign_id, slot_id):
    slot = _brand_slot(request, campaign_id, slot_id)
    latest = services.latest_asset(slot)
    context = {
        "slot": slot,
        "campaign": slot.campaign,
        "latest": latest,
        "assets": slot.assets.prefetch_related("reviews"),
        "form": ReviewForm(),
        "can_review": slot.status == Slot.Status.IN_REVIEW
        and latest
        and latest.status == Asset.Status.IN_REVIEW,
        "revisions_left": max(0, services.settings.MAX_REVISIONS - slot.revisions_used),
        "snapshots": list(slot.post.snapshots.all()[:30]) if hasattr(slot, "post") else [],
        **_post_context(slot),
    }
    return render(request, "content/review.html", context)


@brand_required
@require_POST
def review_action(request, campaign_id, slot_id):
    slot = _brand_slot(request, campaign_id, slot_id)
    form = ReviewForm(request.POST)
    asset = services.latest_asset(slot)
    if form.is_valid() and asset:
        try:
            services.brand_review(
                slot, asset, request.user, form.cleaned_data["decision"], form.cleaned_data["comment"]
            )
            if form.cleaned_data["decision"] == "approved":
                messages.success(
                    request, "Approved. The creator gives a final OK and picks the go-live time."
                )
            else:
                messages.info(request, "Feedback sent to the creator.")
        except services.ContentError as exc:
            messages.error(request, str(exc))
    return redirect("content:review", campaign_id=campaign_id, slot_id=slot_id)


# --- Files ---------------------------------------------------------------------------------


def asset_file(request, asset_id):
    """Private download: only the slot's creator, the campaign's brand, and ops."""
    if not request.user.is_authenticated:
        raise Http404
    asset = get_object_or_404(
        Asset.objects.select_related("slot__creator", "slot__campaign__brand"), pk=asset_id
    )
    user = request.user
    allowed = (
        user.is_ops or asset.slot.creator.user_id == user.pk or asset.slot.campaign.brand.user_id == user.pk
    )
    if not allowed:
        raise PermissionDenied
    return FileResponse(asset.file.open("rb"), content_type=asset.content_type, filename=asset.original_name)


def public_asset(request, token):
    """Time-limited public link, used only so Instagram's servers can fetch the approved file."""
    try:
        asset = services.asset_from_public_token(token)
    except (signing.BadSignature, Asset.DoesNotExist) as exc:
        raise Http404 from exc
    if asset.status != Asset.Status.FINAL:
        raise Http404
    return FileResponse(asset.file.open("rb"), content_type=asset.content_type)
