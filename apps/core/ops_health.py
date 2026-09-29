"""Numbers for the ops page: funnel, things that are stuck, and integration health.

Ops-only. This is the one place that looks at both brand prices and creator fees (for margin).
"""

from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

FUNNEL_DAYS = 30
SCHEDULER_STALE = timedelta(minutes=30)


def funnel(now=None, days=FUNNEL_DAYS):
    from apps.campaigns.models import Campaign
    from apps.offers.models import Offer, Slot
    from apps.payments.models import Order

    now = now or timezone.now()
    since = now - timedelta(days=days)
    campaigns = Campaign.objects.filter(created_at__gte=since)
    live = [Slot.Status.LIVE, Slot.Status.VERIFIED]
    steps = [
        ("Campaigns created", campaigns.count()),
        (
            "Brief confirmed",
            campaigns.exclude(status__in=[Campaign.Status.DRAFT, Campaign.Status.BRIEF_READY]).count(),
        ),
        ("Offers sent", campaigns.filter(slots__isnull=False).distinct().count()),
        ("Paid", campaigns.filter(orders__status=Order.Status.PAID).distinct().count()),
        ("A post went live", campaigns.filter(slots__status__in=live).distinct().count()),
        ("Completed", campaigns.filter(status=Campaign.Status.COMPLETED).count()),
    ]
    top = steps[0][1] or 0
    rows = [{"label": label, "count": n, "pct": round(n * 100 / top) if top else None} for label, n in steps]

    offers = Offer.objects.filter(created_at__gte=since).aggregate(
        sent=Count("id"),
        accepted=Count("id", filter=Q(status=Offer.Status.ACCEPTED)),
        declined=Count("id", filter=Q(status=Offer.Status.DECLINED)),
        expired=Count("id", filter=Q(status=Offer.Status.EXPIRED)),
    )
    answered = offers["accepted"] + offers["declined"] + offers["expired"]
    offers["acceptance_pct"] = round(offers["accepted"] * 100 / answered) if answered else None

    paid_slots = Slot.objects.filter(order__status=Order.Status.PAID, order__paid_at__gte=since).exclude(
        status=Slot.Status.CANCELLED
    )
    money = paid_slots.aggregate(gmv=Sum("brand_price"), fees=Sum("creator_fee"))
    gmv, fees = money["gmv"] or 0, money["fees"] or 0
    return {
        "days": days,
        "steps": rows,
        "offers": offers,
        "gmv": gmv,
        "margin": gmv - fees,
        "margin_pct": round((gmv - fees) * 100 / gmv) if gmv else None,
    }


def stuck(now=None):
    """Things a person should look at, grouped. Each item has a label and a link."""
    from apps.campaigns.models import Campaign
    from apps.campaigns.services import needs_review
    from apps.content.models import Post
    from apps.creators.models import CreatorProfile
    from apps.offers.models import Slot
    from apps.payments.models import Payout, Refund

    now = now or timezone.now()
    groups = []

    def add(title, qs, label, url, hint=""):
        items = [{"label": label(o), "url": url(o)} for o in qs[:10]]
        if items:
            groups.append({"title": title, "count": qs.count(), "items": items, "hint": hint})

    waiting = [
        c
        for c in Campaign.objects.filter(
            status=Campaign.Status.SHORTLISTED, ops_approved_at__isnull=True
        ).select_related("brand")
        if c.confirmed_brief and needs_review(c.confirmed_brief)
    ]
    if waiting:
        groups.append(
            {
                "title": "Sensitive campaigns waiting for approval",
                "count": len(waiting),
                "hint": "Offers can't go out until approved.",
                "items": [
                    {
                        "label": f"{c.title} · {c.brand.company_name}",
                        "url": reverse("admin:campaigns_campaign_change", args=[c.pk]),
                    }
                    for c in waiting[:10]
                ],
            }
        )
    add(
        "Publishing failed",
        Post.objects.filter(status=Post.Status.FAILED).select_related("slot__creator"),
        lambda p: f"@{p.slot.creator.ig_username} · {p.last_error or 'no details'}"[:120],
        lambda p: reverse("admin:content_post_change", args=[p.pk]),
        "The creator was asked to post it themselves. Check it goes live.",
    )
    add(
        "Posts on hold (missing or edited)",
        Slot.objects.filter(status=Slot.Status.ON_HOLD).select_related("creator", "campaign"),
        lambda s: f"@{s.creator.ig_username} · {s.campaign.title}",
        lambda s: reverse("admin:offers_slot_change", args=[s.pk]),
    )
    add(
        "Refunds that failed",
        Refund.objects.filter(status=Refund.Status.FAILED).select_related("order"),
        lambda r: f"{r.order.invoice_number} · {r.error or 'no details'}"[:120],
        lambda r: reverse("admin:payments_refund_change", args=[r.pk]),
        "Retry in the payment dashboard or refund manually.",
    )
    add(
        "Payouts ready for more than 3 days",
        Payout.objects.filter(
            status=Payout.Status.RELEASABLE, updated_at__lte=now - timedelta(days=3)
        ).select_related("creator"),
        lambda p: p.creator.display_name,
        lambda p: reverse("admin:payments_payout_change", args=[p.pk]),
    )
    add(
        "Creators in active campaigns who must reconnect Instagram",
        CreatorProfile.objects.filter(ig_needs_reconnect=True, slots__status__in=Slot.IN_PROGRESS).distinct(),
        lambda c: f"{c.display_name} · @{c.ig_username}",
        lambda c: reverse("admin:creators_creatorprofile_change", args=[c.pk]),
        "Publishing and post checks need their Instagram access.",
    )
    add(
        "Slots nobody could fill (last 30 days)",
        Slot.objects.filter(
            status=Slot.Status.UNFILLED, updated_at__gte=now - timedelta(days=30)
        ).select_related("campaign"),
        lambda s: f"{s.campaign.title} · slot {s.position}",
        lambda s: reverse("admin:offers_slot_change", args=[s.pk]),
        "A sign of thin supply in that niche.",
    )
    return groups


def integrations(now=None):
    from apps.campaigns.models import ProductBrief
    from apps.content.models import Post
    from apps.creators.models import CreatorProfile

    from .models import JobHeartbeat

    now = now or timezone.now()
    week = now - timedelta(days=7)
    beat = JobHeartbeat.objects.filter(name="process_deadlines").first()
    briefs = ProductBrief.objects.filter(created_at__gte=week).exclude(source=ProductBrief.Source.EDITED)
    total_briefs = briefs.count()
    fallback = briefs.filter(source=ProductBrief.Source.RULES).count()
    posts = Post.objects.filter(created_at__gte=week, method=Post.Method.API)
    connected = CreatorProfile.objects.filter(ig_connected_at__isnull=False)
    rows = [
        {
            "name": "Scheduler",
            "mode": "Celery Beat / devserver thread",
            "ok": bool(beat and now - beat.last_run_at < SCHEDULER_STALE),
            "detail": f"last run {timezone.localtime(beat.last_run_at):%d %b %H:%M}" if beat else "never ran",
        },
        {
            "name": "AI briefs",
            "mode": settings.LLM_PROVIDER,
            "ok": settings.LLM_PROVIDER == "rules" or not total_briefs or fallback < total_briefs,
            "detail": (
                f"{total_briefs} briefs this week"
                + (f", {fallback} used the rule-based fallback" if settings.LLM_PROVIDER != "rules" else "")
            ),
        },
        {
            "name": "Instagram",
            "mode": settings.INSTAGRAM_PROVIDER,
            "ok": not connected.filter(ig_needs_reconnect=True).exists()
            and not posts.filter(status=Post.Status.FAILED).exists(),
            "detail": (
                f"{connected.filter(ig_needs_reconnect=True).count()} of {connected.count()} creators must "
                f"reconnect · {posts.filter(status=Post.Status.FAILED).count()} of {posts.count()} "
                "auto-posts failed this week"
            ),
        },
        {
            "name": "Payments",
            "mode": settings.PAYMENTS_PROVIDER,
            "ok": settings.PAYMENTS_PROVIDER == "mock"
            or bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_WEBHOOK_SECRET),
            "detail": "test mode (no real money)"
            if settings.PAYMENTS_PROVIDER == "mock"
            else ("keys configured" if settings.RAZORPAY_KEY_ID else "keys missing"),
        },
    ]
    return rows
