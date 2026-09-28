from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.brands.views import get_brand
from apps.core.forms import StyledFormMixin
from apps.core.money import rupees_to_paise
from apps.core.permissions import brand_required, creator_required, ops_required
from apps.offers.models import Slot

from . import services
from .models import Dispute


class ReportForm(StyledFormMixin, forms.Form):
    category = forms.ChoiceField(label="What's wrong?")
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), max_length=3000, label="Tell us what happened"
    )

    def __init__(self, *args, party, **kwargs):
        super().__init__(*args, **kwargs)
        cats = Dispute.BRAND_CATEGORIES if party == Dispute.Party.BRAND else Dispute.CREATOR_CATEGORIES
        self.fields["category"].choices = [(c.value, c.label) for c in cats]


class ResolveForm(StyledFormMixin, forms.Form):
    resolution = forms.ChoiceField(choices=Dispute.Resolution.choices)
    refund_rupees = forms.IntegerField(
        required=False, min_value=1, label="Refund to brand (₹, excl. GST) for a split"
    )
    note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), label="Explanation (shown to both sides)"
    )


def _raise(request, slot, party, redirect_to):
    form = ReportForm(request.POST, party=party)
    if not form.is_valid():
        messages.error(request, "Choose what's wrong and describe it.")
        return redirect_to
    try:
        services.raise_dispute(
            slot, request.user, party, form.cleaned_data["category"], form.cleaned_data["description"]
        )
        messages.success(
            request, "Thanks. Our team will review it within 2 working days. Payment is on hold until then."
        )
    except services.DisputeError as exc:
        messages.error(request, str(exc))
    return redirect_to


@brand_required
@require_POST
def brand_report(request, campaign_id, slot_id):
    slot = get_object_or_404(Slot, pk=slot_id, campaign_id=campaign_id, campaign__brand=get_brand(request))
    return _raise(
        request,
        slot,
        Dispute.Party.BRAND,
        redirect("content:review", campaign_id=campaign_id, slot_id=slot_id),
    )


@creator_required
@require_POST
def creator_report(request, slot_id):
    slot = get_object_or_404(Slot, pk=slot_id, creator__user=request.user)
    return _raise(request, slot, Dispute.Party.CREATOR, redirect("content:workspace", slot_id=slot_id))


@ops_required
def ops_list(request):
    disputes = Dispute.objects.select_related("slot__campaign__brand", "slot__creator", "raised_by")
    return render(
        request,
        "disputes/list.html",
        {
            "open": disputes.filter(status=Dispute.Status.OPEN),
            "resolved": disputes.filter(status=Dispute.Status.RESOLVED)[:30],
        },
    )


@ops_required
def ops_detail(request, pk):
    dispute = get_object_or_404(
        Dispute.objects.select_related("slot__campaign__brand", "slot__creator"), pk=pk
    )
    form = ResolveForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        amount = rupees_to_paise(form.cleaned_data["refund_rupees"] or 0)
        try:
            services.resolve(
                dispute,
                form.cleaned_data["resolution"],
                form.cleaned_data["note"],
                request.user,
                refund_amount=amount,
            )
            messages.success(request, "Dispute resolved. Both sides have been notified.")
            return redirect("disputes:detail", pk=pk)
        except services.DisputeError as exc:
            messages.error(request, str(exc))
    return render(
        request, "disputes/detail.html", {"dispute": dispute, "form": form, **services.evidence(dispute)}
    )


def report_form(party):
    """Unbound form for templates."""
    return ReportForm(party=party)
