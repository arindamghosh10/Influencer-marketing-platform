"""Contract signing and consent ledger.

Flow: a feature calls `prepare_signature()` with the contract kind, the context to render it and
the consents it grants. The user reads the exact text, types their name, confirms with an emailed
one-time code, and only then are the Agreement and ConsentEvents written. The stored text and its
SHA-256 hash prove exactly what was signed.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.events import client_ip, record

from .models import Agreement, AgreementKind, ConsentEvent, ConsentScope, OneTimeCode

# Bump a version whenever a template's legal text changes; users re-sign on next action.
CURRENT_VERSIONS = {
    AgreementKind.CREATOR_PLATFORM: "1.0",
    AgreementKind.BRAND_PLATFORM: "1.0",
    AgreementKind.CREATOR_CAMPAIGN: "1.0",
    AgreementKind.BRAND_ORDER: "1.0",
}


def latest_campaign_agreement(user, kind, campaign, since):
    """The agreement this user signed for `campaign` after `since` (e.g. after an offer was made)."""
    return (
        Agreement.objects.filter(user=user, kind=kind, campaign=campaign, signed_at__gte=since)
        .order_by("-signed_at")
        .first()
    )


SESSION_KEY = "pending_agreement"
OTP_TTL = timedelta(minutes=10)
OTP_MAX_ATTEMPTS = 5


def render_agreement(kind, context):
    version = CURRENT_VERSIONS[kind]
    body = render_to_string(f"contracts/{kind}_v{version}.html", context)
    return version, body, hashlib.sha256(body.encode()).hexdigest()


def has_current_agreement(user, kind):
    return Agreement.objects.filter(user=user, kind=kind, version=CURRENT_VERSIONS[kind]).exists()


def prepare_signature(request, kind, context, consents, next_url, campaign=None):
    version, body, sha = render_agreement(kind, context)
    request.session[SESSION_KEY] = {
        "kind": kind,
        "version": version,
        "body": body,
        "sha256": sha,
        "consents": [str(c) for c in consents],
        "next_url": next_url,
        "campaign_id": campaign.pk if campaign else None,
        "otp_id": None,
        "signed_name": "",
    }


def pending(request):
    return request.session.get(SESSION_KEY)


def _hash_code(code):
    return hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


def send_otp(request, signed_name):
    data = pending(request)
    code = f"{secrets.randbelow(1_000_000):06d}"
    otp = OneTimeCode.objects.create(
        user=request.user,
        purpose=f"sign:{data['kind']}",
        code_hash=_hash_code(code),
        expires_at=timezone.now() + OTP_TTL,
    )
    data["otp_id"] = otp.pk
    data["signed_name"] = signed_name
    request.session[SESSION_KEY] = data
    send_mail(
        f"Your signing code: {code}",
        f"Use {code} to sign your {settings.PLATFORM_NAME} agreement. It expires in 10 minutes.\n"
        "If you didn't request this, ignore this email.",
        None,
        [request.user.email],
    )
    return code


def verify_and_sign(request, code):
    """Returns (agreement, error_message)."""
    data = pending(request)
    if not data or not data.get("otp_id"):
        return None, "Your signing session expired. Please start again."
    otp = OneTimeCode.objects.filter(pk=data["otp_id"], user=request.user, used_at__isnull=True).first()
    if otp is None or otp.expires_at < timezone.now():
        return None, "This code has expired. Request a new one."
    if otp.attempts >= OTP_MAX_ATTEMPTS:
        return None, "Too many attempts. Request a new code."
    if not hmac.compare_digest(otp.code_hash, _hash_code(code.strip())):
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        return None, "That code isn't right. Check your email and try again."
    otp.used_at = timezone.now()
    otp.save(update_fields=["used_at"])

    # The text is re-hashed so a tampered session can never produce a valid signature.
    if hashlib.sha256(data["body"].encode()).hexdigest() != data["sha256"]:
        return None, "The agreement text changed. Please review it again."
    ip = client_ip(request)
    ua = request.META.get("HTTP_USER_AGENT", "")[:400]
    agreement = Agreement.objects.create(
        user=request.user,
        kind=data["kind"],
        version=data["version"],
        campaign_id=data["campaign_id"],
        body=data["body"],
        sha256=data["sha256"],
        signed_name=data["signed_name"],
        signed_at=timezone.now(),
        ip_address=ip,
        user_agent=ua,
        otp_verified=True,
    )
    for scope in data["consents"]:
        ConsentEvent.objects.create(
            user=request.user,
            scope=scope,
            action=ConsentEvent.Action.GRANTED,
            agreement=agreement,
            campaign_id=data["campaign_id"],
            ip_address=ip,
            user_agent=ua,
        )
    record(
        "agreement.signed",
        f"{request.user} signed {agreement.get_kind_display()} v{agreement.version}",
        actor=request.user,
        target=agreement,
        data={"sha256": agreement.sha256},
        request=request,
    )
    del request.session[SESSION_KEY]
    return agreement, None


def current_consents(user):
    """{scope: latest ConsentEvent} for every scope the user has ever acted on."""
    latest = {}
    for event in ConsentEvent.objects.filter(user=user, campaign__isnull=True).order_by("created_at"):
        latest[event.scope] = event
    return latest


def has_consent(user, scope):
    event = current_consents(user).get(scope)
    return bool(event and event.action == ConsentEvent.Action.GRANTED)


# Consents a user can switch off themselves at any time from the consent centre.
REVOCABLE = {
    ConsentScope.MARKETING,
    ConsentScope.AI_LIKENESS,
    ConsentScope.INSTAGRAM_PUBLISH,
}


def set_consent(request, scope, granted):
    ConsentEvent.objects.create(
        user=request.user,
        scope=scope,
        action=ConsentEvent.Action.GRANTED if granted else ConsentEvent.Action.REVOKED,
        ip_address=client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:400],
    )
    record(
        "consent.changed",
        f"{request.user} {'granted' if granted else 'revoked'} {scope}",
        actor=request.user,
        target=request.user,
        request=request,
    )
