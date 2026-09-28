from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

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
    from django.contrib import messages

    from apps.offers.services import process_deadlines

    if request.method == "POST":
        result = process_deadlines()
        messages.success(
            request,
            f"Scheduled jobs ran: {result['expired_offers']} offers expired, "
            f"{result['released_slots']} unpaid slots released.",
        )
    return redirect("core:ops")


@ops_required
def ops_dashboard(request):
    from apps.brands.models import BrandProfile
    from apps.campaigns.models import Campaign
    from apps.creators.models import CreatorProfile

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
    }
    return render(request, "core/ops.html", context)
