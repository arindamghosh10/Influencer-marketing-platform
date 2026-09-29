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
        days = 0
        if settings.DEBUG:
            try:
                days = max(0, min(int(request.POST.get("days") or 0), 60))
            except ValueError:
                days = 0
        result = process_deadlines(timezone.now() + timedelta(days=days))
        summary = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in result.items())
        when = f" as if {days} day{'s' if days != 1 else ''} had passed" if days else ""
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
