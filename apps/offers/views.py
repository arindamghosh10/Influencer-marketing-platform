from django import forms
from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.contracts import services as contracts
from apps.contracts.models import AgreementKind, ConsentScope
from apps.core.forms import StyledFormMixin
from apps.core.money import format_inr
from apps.core.permissions import creator_required

from . import services
from .models import Offer
from .views_models import CreatorOfferView


class DeclineForm(StyledFormMixin, forms.Form):
    reason = forms.ChoiceField(choices=Offer.DeclineReason.choices, label="Why are you declining?")
    note = forms.CharField(required=False, max_length=300, label="Anything else? (optional)")


def _offer(request, pk):
    return get_object_or_404(
        Offer.objects.select_related("slot__campaign__brand", "creator"),
        pk=pk,
        creator__user=request.user,
    )


@creator_required
def detail(request, pk):
    offer = _offer(request, pk)
    if offer.viewed_at is None:
        offer.viewed_at = timezone.now()
        offer.save(update_fields=["viewed_at"])
    open_ = offer.status == Offer.Status.PENDING and offer.expires_at > timezone.now()
    return render(
        request,
        "offers/detail.html",
        {"offer": CreatorOfferView.build(offer), "open": open_, "decline_form": DeclineForm()},
    )


@creator_required
@require_POST
def accept(request, pk):
    offer = _offer(request, pk)
    if offer.status != Offer.Status.PENDING or offer.expires_at <= timezone.now():
        messages.error(request, "This offer is no longer open.")
        return redirect("offers:detail", pk=pk)
    view = CreatorOfferView.build(offer)
    creator = offer.creator
    campaign = offer.slot.campaign
    consents = [ConsentScope.PAID_ADS_USAGE] if campaign.paid_ads_allowed else []
    if view.ai_likeness:
        consents.append(ConsentScope.AI_LIKENESS)
    contracts.prepare_signature(
        request,
        AgreementKind.CREATOR_CAMPAIGN,
        {
            "platform_name": settings.PLATFORM_NAME,
            "legal_name": creator.legal_name or creator.display_name,
            "ig_username": creator.ig_username,
            "today": timezone.localdate().strftime("%d %B %Y"),
            "brand_name": view.brand_name,
            "campaign_title": view.campaign_title,
            "product_name": view.product_name,
            "deliverable": view.deliverable,
            "ai_likeness": view.ai_likeness,
            "content_deadline": view.content_deadline.strftime("%d %B %Y") if view.content_deadline else "",
            "must_say": view.must_say,
            "must_not_say": view.must_not_say,
            "risky_claims": view.risky_claims,
            "fee": format_inr(view.fee),
            "creator_gst": format_inr(view.gst) if view.gst else "",
            "tds": format_inr(view.tds),
            "tds_rate": f"{view.tds_rate_pct:g}%",
            "net": format_inr(view.net),
            "verification_days": view.verification_days,
            "min_live_days": view.min_live_days,
            "usage_rights_days": view.usage_rights_days,
            "paid_ads": view.paid_ads,
        },
        consents,
        next_url=reverse("offers:complete", args=[offer.pk]),
        campaign=campaign,
    )
    return redirect("contracts:sign")


@creator_required
def complete(request, pk):
    """Landing point after the campaign agreement is signed."""
    offer = _offer(request, pk)
    agreement = contracts.latest_campaign_agreement(
        request.user, AgreementKind.CREATOR_CAMPAIGN, offer.slot.campaign, since=offer.created_at
    )
    if agreement is None:
        messages.error(request, "Please sign the campaign agreement to accept.")
        return redirect("offers:detail", pk=pk)
    try:
        services.accept(offer, agreement)
    except services.OfferError as exc:
        messages.error(request, f"{exc} Your signature has been kept on record, but no work is expected.")
        return redirect("offers:detail", pk=pk)
    messages.success(
        request,
        "Accepted! We'll let you know as soon as the brand's payment is secured, and then you can start.",
    )
    return redirect("creators:dashboard")


@creator_required
@require_POST
def decline(request, pk):
    offer = _offer(request, pk)
    form = DeclineForm(request.POST)
    if form.is_valid():
        try:
            services.decline(offer, form.cleaned_data["reason"], form.cleaned_data["note"])
            messages.info(
                request, "Offer declined. Thanks for letting us know; it helps us send better offers."
            )
        except services.OfferError as exc:
            messages.error(request, str(exc))
    return redirect("creators:dashboard")
