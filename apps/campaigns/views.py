from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.brands.views import get_brand
from apps.core.events import events_for, record
from apps.core.permissions import brand_required
from apps.core.pricing import gst
from apps.matching import services as matching
from apps.matching.models import MatchCandidate
from apps.matching.views_models import brand_candidates
from apps.niches.models import Niche, SensitiveCategory

from . import services
from .forms import AddCreatorsForm, BriefEditForm, CampaignForm
from .models import Campaign

STAGES = [
    ("brief", "Brief"),
    ("creators", "Creators"),
    ("offers", "Offers"),
    ("content", "Content"),
    ("live", "Live"),
    ("verified", "Verified"),
]
STAGE_OF_STATUS = {
    Campaign.Status.DRAFT: "brief",
    Campaign.Status.BRIEF_READY: "brief",
    Campaign.Status.BRIEF_CONFIRMED: "creators",
    Campaign.Status.SHORTLISTED: "offers",
    Campaign.Status.OFFERS_OUT: "offers",
    Campaign.Status.ACTIVE: "content",
    Campaign.Status.COMPLETED: "verified",
}
# Once creators are chosen, the brief and settings are frozen: creators accept based on them.
LOCKED = {
    Campaign.Status.SHORTLISTED,
    Campaign.Status.OFFERS_OUT,
    Campaign.Status.ACTIVE,
    Campaign.Status.COMPLETED,
    Campaign.Status.CANCELLED,
}


def brand_slots(campaign):
    """Brand-facing slot rows. Only brand prices are exposed."""
    from django.urls import reverse

    from apps.offers.models import Offer, Slot

    rows = []
    for slot in campaign.slots.prefetch_related("offers__creator").select_related("post"):
        offer = slot.current_offer
        creator = slot.creator or (offer.creator if offer else None)
        price = slot.brand_price or (offer.brand_price if offer else 0)
        tried = [o for o in slot.offers.all() if o.status in (Offer.Status.DECLINED, Offer.Status.EXPIRED)]
        rows.append(
            {
                "id": slot.pk,
                "position": slot.position,
                "status": slot.status,
                "status_label": slot.get_status_display(),
                "creator_name": creator.display_name if creator else "",
                "creator_handle": creator.ig_username if creator else "",
                "price": price if slot.status != Slot.Status.UNFILLED else 0,
                "offer_expires_at": offer.expires_at
                if offer and offer.status == Offer.Status.PENDING
                else None,
                "payment_due_at": slot.payment_due_at if slot.status == Slot.Status.ACCEPTED else None,
                "replaced": [f"{o.creator.display_name} ({o.get_status_display().lower()})" for o in tried],
                "cancellable": slot.status in (Slot.Status.OFFERING, Slot.Status.ACCEPTED),
                "needs_review": slot.status == Slot.Status.IN_REVIEW,
                "detail_url": reverse("content:review", args=[campaign.pk, slot.pk])
                if slot.status in (*Slot.IN_PROGRESS, Slot.Status.VERIFIED)
                else "",
                "permalink": slot.post.permalink if hasattr(slot, "post") else "",
            }
        )
    return rows


def _payable_summary(campaign):
    from apps.payments.services import payable_slots
    from apps.payments.tax import gst_split

    slots = list(payable_slots(campaign))
    if not slots:
        return None
    subtotal = sum(s.brand_price for s in slots)
    tax = gst_split(subtotal, campaign.brand.gstin).total
    return {"count": len(slots), "subtotal": subtotal, "gst": tax, "total": subtotal + tax}


def _campaign(request, pk):
    brand = get_brand(request)
    return get_object_or_404(Campaign.objects.select_related("brand"), pk=pk, brand=brand)


@brand_required
def create(request):
    brand = get_brand(request)
    if brand is None:
        messages.info(request, "First, tell us about your brand.")
        return redirect("brands:profile")
    form = CampaignForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        campaign = form.save(commit=False)
        campaign.brand = brand
        campaign.save()
        record(
            "campaign.created",
            f"Campaign '{campaign}' created",
            actor=request.user,
            target=campaign,
            request=request,
        )
        brief = services.generate_brief(campaign, actor=request.user)
        if brief.fetch_error:
            messages.warning(
                request,
                f"We couldn't read the product page ({brief.fetch_error}), so the "
                "brief is based on your notes. Please check and complete it.",
            )
        return redirect("campaigns:detail", pk=campaign.pk)
    return render(request, "campaigns/create.html", {"form": form})


def _selection_summary(run):
    if run is None:
        return None
    chosen = [c for c in run.candidates.all() if c.selected]
    subtotal = sum(c.brand_price for c in chosen)
    tax = gst(subtotal, settings.GST_RATE_BPS)
    return {
        "count": len(chosen),
        "subtotal": subtotal,
        "gst": tax,
        "total": subtotal + tax,
        "budget": run.selection_budget,
        "over_budget": subtotal > run.selection_budget,
    }


@brand_required
def detail(request, pk):
    campaign = _campaign(request, pk)
    brief = campaign.current_brief
    run = campaign.match_runs.first()
    niche_names = {}
    if brief:
        niche_names = dict(
            Niche.objects.filter(slug__in=brief.data.get("niche_slugs", [])).values_list("slug", "name")
        )
    restricted = brief.data.get("restricted_category") if brief else ""
    context = {
        "campaign": campaign,
        "brief": brief,
        "niche_names": [niche_names.get(s, s) for s in (brief.data.get("niche_slugs", []) if brief else [])],
        "restricted_label": SensitiveCategory(restricted).label if restricted else "",
        "blockers": services.brief_blockers(brief) if brief else [],
        "needs_review": services.needs_review(brief) if brief else False,
        "run": run,
        "candidates": brand_candidates(run) if run else [],
        "summary": _selection_summary(run),
        "stages": STAGES,
        "stage": STAGE_OF_STATUS.get(campaign.status, "brief"),
        "events": events_for(campaign)[:30],
        "editable": campaign.status == Campaign.Status.BRIEF_CONFIRMED,
        "locked": campaign.status in LOCKED,
        "can_repeat": services.can_repeat(campaign),
        "can_add_creators": campaign.status in _top_up_statuses(),
        "pending_top_up": run.is_pending_top_up if run else False,
    }
    if campaign.status == Campaign.Status.SHORTLISTED:
        from apps.offers.services import send_blockers

        context["send_blockers"] = send_blockers(campaign)
    if campaign.status in (Campaign.Status.OFFERS_OUT, Campaign.Status.ACTIVE, Campaign.Status.COMPLETED):
        from apps.payments.models import Order

        context["slots"] = brand_slots(campaign)
        context["payable"] = _payable_summary(campaign)
        context["orders"] = campaign.orders.filter(status=Order.Status.PAID)
        from apps.reports import analytics

        posts = list(analytics.brand_posts(campaign.brand, campaign))
        if posts:
            chart = analytics.views_per_post(posts)
            context["results"] = analytics.totals(posts, analytics.brand_spend(campaign.brand, campaign))
            context["chart"] = chart
            context["chart_table"] = analytics.as_table(chart)
            context["creator_rows"] = analytics.creator_rows(campaign)
    return render(request, "campaigns/detail.html", context)


@brand_required
@require_POST
def send_offers(request, pk):
    from apps.offers import services as offers

    campaign = _campaign(request, pk)
    try:
        slots = offers.send_offers(campaign, request.user)
    except offers.OfferError as exc:
        messages.error(request, str(exc))
        return redirect("campaigns:detail", pk=pk)
    messages.success(
        request,
        f"Offers sent to {len(slots)} creators. They have {settings.OFFER_EXPIRY_HOURS} hours to reply; "
        "we'll notify you as they do.",
    )
    return redirect("campaigns:detail", pk=pk)


@brand_required
@require_POST
def cancel_slot(request, pk, slot_id):
    from apps.offers import services as offers
    from apps.offers.models import Slot

    campaign = _campaign(request, pk)
    slot = get_object_or_404(Slot, pk=slot_id, campaign=campaign)
    try:
        offers.cancel_slot(slot, request.user)
        messages.info(request, "Removed. You won't be charged for this creator.")
    except offers.OfferError as exc:
        messages.error(request, str(exc))
    return redirect("campaigns:detail", pk=pk)


@brand_required
def edit(request, pk):
    campaign = _campaign(request, pk)
    if campaign.status in LOCKED:
        messages.warning(request, "Creators are already selected; settings can't change now.")
        return redirect("campaigns:detail", pk=pk)
    form = CampaignForm(request.POST or None, request.FILES or None, instance=campaign)
    if request.method == "POST" and form.is_valid():
        product_changed = {"product_url", "product_notes"} & set(form.changed_data)
        form.save()
        record(
            "campaign.updated",
            "Campaign settings updated",
            actor=request.user,
            target=campaign,
            request=request,
        )
        if product_changed:
            services.generate_brief(campaign, actor=request.user)
            messages.info(
                request, "Product details changed, so we re-read the product. Please review the new brief."
            )
        return redirect("campaigns:detail", pk=pk)
    return render(request, "campaigns/create.html", {"form": form, "campaign": campaign})


@brand_required
def edit_brief(request, pk):
    campaign = _campaign(request, pk)
    brief = campaign.current_brief
    if brief is None or campaign.status in LOCKED:
        return redirect("campaigns:detail", pk=pk)
    form = BriefEditForm.from_brief(brief.data, request.POST or None)
    if request.method == "POST" and form.is_valid():
        services.save_edited_brief(campaign, form.merged(brief.data), request.user)
        messages.success(request, "Brief updated. Review it and confirm when ready.")
        return redirect("campaigns:detail", pk=pk)
    return render(request, "campaigns/edit_brief.html", {"campaign": campaign, "form": form})


@brand_required
@require_POST
def regenerate_brief(request, pk):
    campaign = _campaign(request, pk)
    if campaign.status not in LOCKED:
        services.generate_brief(campaign, actor=request.user)
        messages.info(request, "We re-read your product page.")
    return redirect("campaigns:detail", pk=pk)


@brand_required
@require_POST
def confirm_brief(request, pk):
    campaign = _campaign(request, pk)
    brief = campaign.current_brief
    if brief is None or brief.confirmed_at:
        return redirect("campaigns:detail", pk=pk)
    blockers = services.brief_blockers(brief)
    if blockers:
        for b in blockers:
            messages.error(request, b)
        return redirect("campaigns:detail", pk=pk)
    if brief.data.get("risky_claims") and request.POST.get("claims_ack") != "1":
        messages.error(
            request, "Please confirm you won't ask creators to make the flagged claims without proof."
        )
        return redirect("campaigns:detail", pk=pk)
    services.confirm_brief(campaign, brief, request.user)
    run = matching.run_matching(campaign)
    record(
        "campaign.matched",
        f"Matched {run.candidates.filter(role='recommended').count()} creators "
        f"from {run.eligible_count} eligible",
        actor=request.user,
        target=campaign,
    )
    messages.success(request, "Brief confirmed. Here are the creators we recommend.")
    return redirect("campaigns:detail", pk=pk)


@brand_required
@require_POST
def rematch(request, pk):
    campaign = _campaign(request, pk)
    if campaign.status == Campaign.Status.BRIEF_CONFIRMED:
        matching.run_matching(campaign)
        messages.success(request, "Refreshed creator recommendations.")
    return redirect("campaigns:detail", pk=pk)


@brand_required
@require_POST
def toggle_candidate(request, pk, candidate_id):
    campaign = _campaign(request, pk)
    run = campaign.match_runs.first()
    mc = get_object_or_404(MatchCandidate, pk=candidate_id, run=run)
    editable = _selection_editable(campaign, run)
    if editable:
        mc.selected = not mc.selected
        mc.save(update_fields=["selected"])
    if not request.htmx:  # plain form post (JavaScript unavailable): reload the page
        return redirect("campaigns:add_creators" if run.is_pending_top_up else "campaigns:detail", pk=pk)
    candidate = next(c for c in brand_candidates(run) if c.id == mc.pk)
    context = {
        "c": candidate,
        "campaign": campaign,
        "summary": _selection_summary(run),
        "editable": editable,
    }
    return render(request, "campaigns/partials/candidate_toggle.html", context)


@brand_required
@require_POST
def confirm_selection(request, pk):
    campaign = _campaign(request, pk)
    run = campaign.match_runs.first()
    summary = _selection_summary(run)
    if campaign.status != Campaign.Status.BRIEF_CONFIRMED or not summary or not summary["count"]:
        messages.error(request, "Select at least one creator.")
        return redirect("campaigns:detail", pk=pk)
    if summary["over_budget"]:
        messages.error(request, "Your selection is over budget. Remove a creator or raise the budget.")
        return redirect("campaigns:detail", pk=pk)
    campaign.status = Campaign.Status.SHORTLISTED
    campaign.save(update_fields=["status", "updated_at"])
    record(
        "campaign.shortlisted",
        f"{summary['count']} creators selected",
        actor=request.user,
        target=campaign,
        data={"subtotal": summary["subtotal"]},
        request=request,
    )
    messages.success(request, "Creators selected. Send them offers when you're ready.")
    return redirect("campaigns:detail", pk=pk)


def _top_up_statuses():
    from apps.offers.services import TOP_UP_STATUSES

    return TOP_UP_STATUSES


def _selection_editable(campaign, run):
    if run.is_pending_top_up:
        return campaign.status in _top_up_statuses()
    return campaign.status == Campaign.Status.BRIEF_CONFIRMED


@brand_required
@require_POST
def repeat(request, pk):
    campaign = _campaign(request, pk)
    if not services.can_repeat(campaign):
        messages.error(request, "Only campaigns with a confirmed brief can be run again.")
        return redirect("campaigns:detail", pk=pk)
    new = services.repeat_campaign(campaign, request.user)
    messages.success(
        request,
        "New campaign created with the same brief and settings. Creators who delivered last time "
        "are selected first when they're available. Check the budget and creators, then confirm.",
    )
    return redirect("campaigns:detail", pk=new.pk)


@brand_required
def add_creators(request, pk):
    """Find and offer more creators for a running campaign."""
    campaign = _campaign(request, pk)
    if campaign.status not in _top_up_statuses():
        messages.warning(request, "Creators can only be added while the campaign is running.")
        return redirect("campaigns:detail", pk=pk)
    run = campaign.match_runs.first()
    pending = run if run and run.is_pending_top_up else None
    form = AddCreatorsForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        pending = matching.run_matching(
            campaign, top_up_budget=form.budget_paise, top_up_count=form.cleaned_data["count"]
        )
        record(
            "campaign.top_up_matched",
            f"Looked for {form.cleaned_data['count']} more creators",
            actor=request.user,
            target=campaign,
        )
        return redirect("campaigns:add_creators", pk=pk)
    if pending and request.method == "GET":
        form = AddCreatorsForm(
            initial={"count": pending.creators_wanted, "budget_rupees": pending.budget // 100}
        )
    context = {
        "campaign": campaign,
        "form": form,
        "run": pending,
        "candidates": brand_candidates(pending) if pending else [],
        "summary": _selection_summary(pending),
        "editable": True,
    }
    if pending:
        from apps.offers.services import send_blockers

        context["send_blockers"] = send_blockers(campaign)
    return render(request, "campaigns/add_creators.html", context)


@brand_required
@require_POST
def send_top_up(request, pk):
    from apps.offers import services as offers

    campaign = _campaign(request, pk)
    try:
        slots = offers.send_top_up(campaign, request.user)
    except offers.OfferError as exc:
        messages.error(request, str(exc))
        return redirect("campaigns:add_creators", pk=pk)
    messages.success(
        request,
        f"Offers sent to {len(slots)} more creator{'s' if len(slots) != 1 else ''}. Pay for each one "
        "once they accept.",
    )
    return redirect("campaigns:detail", pk=pk)


@brand_required
@require_POST
def discard_top_up(request, pk):
    campaign = _campaign(request, pk)
    run = campaign.match_runs.first()
    if run and run.is_pending_top_up:
        run.delete()
        messages.info(request, "Discarded. No offers were sent.")
    return redirect("campaigns:detail", pk=pk)
