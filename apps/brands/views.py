from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.contracts import services as contracts
from apps.contracts.models import AgreementKind, ConsentScope
from apps.core.events import notify, record
from apps.core.permissions import brand_required

from . import services
from .forms import BrandProfileForm
from .models import BrandProfile


def get_brand(request):
    return BrandProfile.objects.filter(user=request.user).first()


@brand_required
def dashboard(request):
    brand = get_brand(request)
    if brand is None:
        return redirect("brands:profile")
    steps = services.onboarding_steps(brand)
    campaigns = brand.campaigns.all()
    actions = []
    for c in campaigns:
        if c.status == c.Status.BRIEF_READY:
            actions.append((c, "Review and confirm the product brief"))
        elif c.status == c.Status.BRIEF_CONFIRMED:
            actions.append((c, "Pick your creators"))
    return render(
        request,
        "brands/dashboard.html",
        {
            "brand": brand,
            "steps": steps,
            "campaigns": campaigns,
            "actions": actions,
            "setup_done": all(done for _k, _l, done in steps),
        },
    )


@brand_required
def profile(request):
    brand = get_brand(request) or BrandProfile(user=request.user)
    form = BrandProfileForm(request.POST or None, instance=brand)
    if request.method == "POST" and form.is_valid():
        website_changed = "website" in form.changed_data
        brand = form.save()
        if website_changed:
            brand.domain_verified_at = None
            brand.save(update_fields=["domain_verified_at"])
        record(
            "brand.profile_updated",
            f"{brand} updated brand profile",
            actor=request.user,
            target=brand,
            request=request,
        )
        messages.success(request, "Brand profile saved.")
        if not contracts.has_current_agreement(request.user, AgreementKind.BRAND_PLATFORM):
            return redirect("brands:agreement")
        return redirect("brands:dashboard")
    if brand.pk:
        brand.ensure_verification_token()
    return render(request, "brands/profile.html", {"form": form, "brand": brand})


@brand_required
@require_POST
def verify_domain(request):
    brand = get_brand(request)
    if brand and services.check_domain_txt(brand):
        record(
            "brand.domain_verified",
            f"{brand} verified {brand.domain}",
            actor=request.user,
            target=brand,
            request=request,
        )
        messages.success(request, f"{brand.domain} verified.")
    else:
        messages.warning(
            request,
            "We couldn't find the TXT record yet. DNS changes can take up to a few hours; try again later.",
        )
    return redirect("brands:profile")


@brand_required
def agreement(request):
    brand = get_brand(request)
    if brand is None:
        return redirect("brands:profile")
    if request.method == "POST":
        contracts.prepare_signature(
            request,
            AgreementKind.BRAND_PLATFORM,
            {
                "platform_name": settings.PLATFORM_NAME,
                "company_name": brand.company_name,
                "gstin": brand.gstin,
                "signer_email": request.user.email,
                "today": timezone.localdate().strftime("%d %B %Y"),
                "brand_review_hours": settings.BRAND_REVIEW_HOURS,
                "usage_rights_days": 90,
            },
            [ConsentScope.TERMS, ConsentScope.DATA_PROCESSING],
            next_url=reverse("brands:submit"),
        )
        return redirect("contracts:sign")
    signed = contracts.has_current_agreement(request.user, AgreementKind.BRAND_PLATFORM)
    return render(request, "brands/agreement.html", {"brand": brand, "signed": signed})


@brand_required
def submit_for_review(request):
    brand = get_brand(request)
    if brand is None:
        return redirect("brands:profile")
    if brand.status in (BrandProfile.Status.DRAFT, BrandProfile.Status.REJECTED):
        brand.status = BrandProfile.Status.PENDING_REVIEW
        brand.save(update_fields=["status", "updated_at"])
        record(
            "brand.submitted",
            f"{brand} submitted for review",
            actor=request.user,
            target=brand,
            request=request,
        )
        notify(
            request.user,
            "Brand account in review",
            "You can already create campaigns and see creator matches. Offers go out to creators "
            "once your account is approved (usually within 1 working day).",
            url=reverse("brands:dashboard"),
        )
    return redirect("brands:dashboard")
