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
from .forms import BriefEditForm, CampaignForm
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
}


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
        "budget": run.campaign.budget,
        "over_budget": subtotal > run.campaign.budget,
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
    }
    return render(request, "campaigns/detail.html", context)


@brand_required
def edit(request, pk):
    campaign = _campaign(request, pk)
    if campaign.status == Campaign.Status.SHORTLISTED:
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
    if brief is None or campaign.status == Campaign.Status.SHORTLISTED:
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
    if campaign.status != Campaign.Status.SHORTLISTED:
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
    if campaign.status == Campaign.Status.BRIEF_CONFIRMED:
        mc.selected = not mc.selected
        mc.save(update_fields=["selected"])
    candidate = next(c for c in brand_candidates(run) if c.id == mc.pk)
    context = {
        "c": candidate,
        "campaign": campaign,
        "summary": _selection_summary(run),
        "editable": campaign.status == Campaign.Status.BRIEF_CONFIRMED,
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
    messages.success(
        request, "Creators selected. Next, we'll send them offers once your account is approved."
    )
    return redirect("campaigns:detail", pk=pk)
