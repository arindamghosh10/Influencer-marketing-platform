from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from . import ops_health
from .permissions import ops_required


def landing(request):
    if request.user.is_authenticated:
        return redirect("core:home")
    return render(request, "core/landing.html")


@login_required
def home(request):
    user = request.user
    if user.is_brand:
        return redirect("brands:dashboard")
    if user.is_creator:
        return redirect("creators:dashboard")
    return redirect("core:ops")


@login_required
def notifications(request):
    items = list(request.user.notifications.all()[:50])
    request.user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
    return render(request, "core/notifications.html", {"items": items})


@ops_required
def run_jobs(request):
    from datetime import timedelta

    from django.conf import settings
    from django.contrib import messages

    from apps.offers.services import process_deadlines

    if request.method == "POST":
        # Local testing only: run the jobs as if some days had passed (e.g. the 7-day
        # verification), so the whole flow can be tried in one sitting.
        days = 0.0
        if settings.DEBUG:
            try:
                days = max(0.0, min(float(request.POST.get("days") or 0), 60.0))
            except ValueError:
                days = 0.0
        result = process_deadlines(timezone.now() + timedelta(days=days))
        summary = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in result.items())
        when = f" as if {days:g} day{'s' if days != 1 else ''} had passed" if days else ""
        messages.success(request, f"Scheduled jobs ran{when}. {summary}.")
    return redirect("core:ops")


@ops_required
def ops_dashboard(request):
    from django.conf import settings

    from apps.brands.models import BrandProfile
    from apps.campaigns.models import Campaign
    from apps.creators.models import CreatorProfile
    from apps.disputes.models import Dispute
    from apps.payments.models import Payout

    from .models import Event

    context = {
        "creators_pending": CreatorProfile.objects.filter(
            status=CreatorProfile.Status.PENDING_REVIEW
        ).select_related("user", "primary_niche"),
        "brands_pending": BrandProfile.objects.filter(
            status=BrandProfile.Status.PENDING_REVIEW
        ).select_related("user"),
        "counts": {
            "creators_approved": CreatorProfile.objects.filter(status=CreatorProfile.Status.APPROVED).count(),
            "brands_approved": BrandProfile.objects.filter(status=BrandProfile.Status.APPROVED).count(),
            "campaigns": Campaign.objects.exclude(status=Campaign.Status.CANCELLED).count(),
        },
        "events": Event.objects.select_related("actor")[:25],
        "open_disputes": Dispute.objects.filter(status=Dispute.Status.OPEN).select_related(
            "slot__campaign", "slot__creator"
        ),
        "payouts_due": Payout.objects.filter(status=Payout.Status.RELEASABLE).select_related("creator"),
        "time_travel": settings.DEBUG,
        "funnel": ops_health.funnel(),
        "stuck": ops_health.stuck(),
        "integrations": ops_health.integrations(),
    }
    return render(request, "core/ops.html", context)


def _legal_context():
    from django.conf import settings

    return {
        "legal_name": settings.PLATFORM_LEGAL_NAME,
        "address": settings.PLATFORM_ADDRESS,
        "grievance_officer": settings.GRIEVANCE_OFFICER,
        "grievance_email": settings.GRIEVANCE_EMAIL,
        "updated": "29 September 2026",
    }


def terms(request):
    return render(request, "core/terms.html", _legal_context())


def privacy(request):
    return render(request, "core/privacy.html", _legal_context())


@login_required
def my_data(request):
    """Download a copy of your data, or ask for it to be erased."""
    import json

    from django.contrib import messages
    from django.http import HttpResponse
    from django.urls import reverse

    from .events import notify, record
    from .models import DataRequest
    from .privacy import export_for

    user = request.user
    if request.method == "POST" and request.POST.get("action") == "export":
        record("privacy.exported", "Personal data exported", actor=user, target=user, request=request)
        body = json.dumps(export_for(user), indent=2, ensure_ascii=False)
        response = HttpResponse(body, content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="my-data-{timezone.localdate():%Y%m%d}.json"'
        return response
    if request.method == "POST" and request.POST.get("action") == "erase":
        if user.data_requests.filter(status=DataRequest.Status.OPEN).exists():
            messages.info(request, "We already have your request and will get back to you.")
        else:
            req = DataRequest.objects.create(user=user, reason=request.POST.get("reason", "")[:2000])
            record(
                "privacy.erasure_requested",
                "Data erasure requested",
                actor=user,
                target=user,
                request=request,
            )
            from apps.accounts.models import User

            for ops in User.objects.filter(role=User.Role.OPS, is_active=True):
                notify(
                    ops,
                    f"Data erasure request from {user.email}",
                    "Respond within 30 days.",
                    url=reverse("admin:core_datarequest_change", args=[req.pk]),
                )
            messages.success(
                request,
                "Request received. We'll confirm within 30 days. Some records (invoices, tax and "
                "payment records, signed agreements) must be kept by law and will be kept only for that.",
            )
        return redirect("core:my_data")
    return render(
        request,
        "core/my_data.html",
        {"open_request": user.data_requests.filter(status=DataRequest.Status.OPEN).first()},
    )
