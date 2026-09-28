import secrets

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.contracts import services as contracts
from apps.contracts.models import AgreementKind, ConsentScope
from apps.core.events import notify, record
from apps.core.permissions import creator_required
from apps.integrations.instagram.base import InstagramError
from apps.integrations.registry import get_provider

from . import services
from .forms import InstagramHandleForm, KycForm, ProfileForm, RatesForm
from .models import CreatorProfile

STEPS = ["profile", "instagram", "rates", "kyc", "agreement"]


def _creator(request):
    creator, _ = CreatorProfile.objects.get_or_create(
        user=request.user, defaults={"display_name": request.user.get_full_name()}
    )
    return creator


def _next_step(creator):
    for key, _label, done in services.onboarding_steps(creator):
        if not done:
            return key
    return None


@creator_required
def dashboard(request):
    creator = _creator(request)
    from apps.offers.models import Offer, Slot
    from apps.offers.views_models import CreatorOfferView
    from apps.payments.services import creator_earnings

    steps = services.onboarding_steps(creator)
    pending = (
        Offer.objects.filter(creator=creator, status=Offer.Status.PENDING, expires_at__gt=timezone.now())
        .select_related("slot__campaign__brand")
        .order_by("expires_at")
    )
    active = (
        Slot.objects.filter(creator=creator, status__in=[Slot.Status.ACCEPTED, Slot.Status.CONFIRMED])
        .select_related("campaign__brand")
        .order_by("-accepted_at")
    )
    context = {
        "creator": creator,
        "steps": steps,
        "next_step": _next_step(creator),
        "rate_band": services.suggested_rate_band(creator),
        "offers": [CreatorOfferView.build(o) for o in pending],
        "active_slots": [
            {
                "brand": s.campaign.brand.company_name,
                "title": s.campaign.title,
                "deliverable": s.campaign.get_deliverable_display(),
                "fee": s.creator_fee,
                "status": s.status,
                "status_label": "Waiting for brand payment"
                if s.status == Slot.Status.ACCEPTED
                else "Payment secured: start creating",
                "deadline": s.campaign.content_deadline,
            }
            for s in active
        ],
        "earnings": creator_earnings(creator),
    }
    return render(request, "creators/dashboard.html", context)


@creator_required
def onboarding(request, step=None):
    creator = _creator(request)
    if step is None:
        return redirect("creators:onboarding_step", step=_next_step(creator) or "profile")
    if step not in STEPS:
        return redirect("creators:onboarding")
    handler = {
        "profile": _step_profile,
        "instagram": _step_instagram,
        "rates": _step_rates,
        "kyc": _step_kyc,
        "agreement": _step_agreement,
    }[step]
    return handler(request, creator)


def _render_step(request, creator, step, context):
    context.update(
        {
            "creator": creator,
            "step": step,
            "steps": services.onboarding_steps(creator),
        }
    )
    return render(request, f"creators/onboarding/{step}.html", context)


def _continue(creator):
    nxt = _next_step(creator)
    if nxt:
        return redirect("creators:onboarding_step", step=nxt)
    return redirect("creators:dashboard")


def _step_profile(request, creator):
    form = ProfileForm(request.POST or None, instance=creator)
    if request.method == "POST" and form.is_valid():
        form.save()
        record(
            "creator.profile_updated",
            f"{creator} updated profile",
            actor=request.user,
            target=creator,
            request=request,
        )
        return _continue(creator)
    return _render_step(request, creator, "profile", {"form": form})


def _step_instagram(request, creator):
    provider = get_provider("instagram")
    form = InstagramHandleForm(request.POST or None)
    if request.method == "POST" and not provider.uses_oauth and form.is_valid():
        token = provider.connect_handle(form.cleaned_data["handle"])
        return _finish_instagram(request, creator, provider, token)
    oauth_url = None
    if provider.uses_oauth:
        state = secrets.token_urlsafe(24)
        request.session["ig_oauth_state"] = state
        oauth_url = provider.authorize_url(state, request.build_absolute_uri(reverse("creators:ig_callback")))
    return _render_step(
        request,
        creator,
        "instagram",
        {
            "form": form,
            "oauth_url": oauth_url,
            "uses_oauth": provider.uses_oauth,
            "suggested": request.session.pop("suggested_niches", None),
        },
    )


@creator_required
def instagram_callback(request):
    creator = _creator(request)
    expected = request.session.pop("ig_oauth_state", None)
    if not expected or request.GET.get("state") != expected or "code" not in request.GET:
        messages.error(request, "Instagram connection was cancelled or expired. Please try again.")
        return redirect("creators:onboarding_step", step="instagram")
    provider = get_provider("instagram")
    try:
        token = provider.exchange_code(
            request.GET["code"], request.build_absolute_uri(reverse("creators:ig_callback"))
        )
    except InstagramError as exc:
        messages.error(request, f"Couldn't connect Instagram: {exc}")
        return redirect("creators:onboarding_step", step="instagram")
    return _finish_instagram(request, creator, provider, token)


def _finish_instagram(request, creator, provider, token):
    try:
        profile = provider.fetch_profile(token)
    except InstagramError as exc:
        messages.error(request, f"Couldn't read your Instagram profile: {exc}")
        return redirect("creators:onboarding_step", step="instagram")
    taken = CreatorProfile.objects.filter(ig_user_id=profile.user_id).exclude(pk=creator.pk)
    if taken.exists():
        messages.error(
            request,
            "This Instagram account is already linked to another profile. "
            "Contact support if this is your account.",
        )
        return redirect("creators:onboarding_step", step="instagram")
    if profile.followers < services.MIN_FOLLOWERS:
        messages.error(
            request,
            f"You need at least {services.MIN_FOLLOWERS:,} followers to join. "
            "Keep creating, and come back soon!",
        )
        return redirect("creators:onboarding_step", step="instagram")
    if profile.followers > services.MAX_FOLLOWERS:
        messages.warning(
            request,
            "We currently work with creators up to 1 lakh followers. We've "
            "saved your details and will reach out when we open to larger creators.",
        )
    suggested = services.apply_instagram_profile(creator, token, profile)
    record(
        "creator.instagram_connected",
        f"{creator} connected Instagram @{profile.username}",
        actor=request.user,
        target=creator,
        data={"followers": profile.followers},
        request=request,
    )
    if suggested and not creator.niches.exists():
        messages.info(
            request,
            "Based on your posts, your content fits: "
            + ", ".join(str(n) for n in suggested)
            + ". You can adjust this in your profile.",
        )
    messages.success(request, f"Connected @{profile.username}.")
    return _continue(creator)


def _step_rates(request, creator):
    form = RatesForm(request.POST or None, instance=creator)
    if request.method == "POST" and form.is_valid():
        form.save()
        return _continue(creator)
    return _render_step(
        request, creator, "rates", {"form": form, "rate_band": services.suggested_rate_band(creator)}
    )


def _step_kyc(request, creator):
    form = KycForm(
        request.POST or None,
        request.FILES or None,
        initial={
            "legal_name": creator.legal_name,
            "bank_account_name": creator.bank_account_name,
            "bank_ifsc": creator.bank_ifsc,
            "gstin": creator.gstin,
        },
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        creator.legal_name = data["legal_name"]
        creator.pan = data["pan"]
        creator.pan_last4 = data["pan"][-4:]
        creator.gstin = data["gstin"]
        creator.bank_account_name = data["bank_account_name"]
        creator.bank_account_number = data["bank_account_number"]
        creator.bank_account_last4 = data["bank_account_number"][-4:]
        creator.bank_ifsc = data["bank_ifsc"]
        creator.kyc_document = data["kyc_document"]
        creator.kyc_status = CreatorProfile.KycStatus.PENDING
        creator.save()
        record(
            "creator.kyc_submitted",
            f"{creator} submitted KYC",
            actor=request.user,
            target=creator,
            request=request,
        )
        return _continue(creator)
    return _render_step(request, creator, "kyc", {"form": form})


CREATOR_PLATFORM_CONSENTS = [
    ConsentScope.TERMS,
    ConsentScope.DATA_PROCESSING,
    ConsentScope.INSTAGRAM_READ,
    ConsentScope.INSTAGRAM_PUBLISH,
    ConsentScope.AI_SCRIPT_HELP,
]


def _step_agreement(request, creator):
    from django.conf import settings

    signed = contracts.has_current_agreement(request.user, AgreementKind.CREATOR_PLATFORM)
    if request.method == "POST" and not signed:
        consents = list(CREATOR_PLATFORM_CONSENTS)
        if creator.allows_ai_likeness:
            consents.append(ConsentScope.AI_LIKENESS)
        contracts.prepare_signature(
            request,
            AgreementKind.CREATOR_PLATFORM,
            {
                "platform_name": settings.PLATFORM_NAME,
                "legal_name": creator.legal_name or creator.display_name,
                "email": request.user.email,
                "ig_username": creator.ig_username,
                "today": timezone.localdate().strftime("%d %B %Y"),
                "verification_days": settings.VERIFICATION_DAYS,
                "min_live_days": settings.MIN_LIVE_DAYS,
            },
            consents,
            next_url=reverse("creators:submit"),
        )
        return redirect("contracts:sign")
    return _render_step(request, creator, "agreement", {"signed": signed})


@creator_required
def submit_for_review(request):
    """Landing point after signing: submit the profile if every step is complete."""
    creator = _creator(request)
    missing = [label for _k, label, done in services.onboarding_steps(creator) if not done]
    if missing:
        messages.warning(request, "Finish these steps first: " + ", ".join(missing))
        return redirect("creators:onboarding")
    if creator.status in (CreatorProfile.Status.DRAFT, CreatorProfile.Status.REJECTED):
        creator.status = CreatorProfile.Status.PENDING_REVIEW
        creator.save(update_fields=["status", "updated_at"])
        record(
            "creator.submitted",
            f"{creator} submitted profile for review",
            actor=request.user,
            target=creator,
            request=request,
        )
        notify(
            request.user,
            "Profile submitted for review",
            "We usually review profiles within 2 working days. We'll notify you here and by email.",
            url=reverse("creators:dashboard"),
        )
        messages.success(request, "You're all set. Your profile is now with our team for review.")
    return redirect("creators:dashboard")


@creator_required
@require_POST
def resync_instagram(request):
    creator = _creator(request)
    provider = get_provider("instagram")
    if not creator.ig_access_token:
        return redirect("creators:onboarding_step", step="instagram")
    from apps.integrations.instagram.base import InstagramToken

    token = InstagramToken(creator.ig_access_token, creator.ig_user_id, creator.ig_token_expires_at)
    try:
        profile = provider.fetch_profile(token)
    except InstagramError as exc:
        messages.error(request, f"Couldn't refresh: {exc}. Please reconnect Instagram.")
        return redirect("creators:onboarding_step", step="instagram")
    services.apply_instagram_profile(creator, token, profile)
    messages.success(request, "Instagram stats refreshed.")
    return redirect("creators:dashboard")
