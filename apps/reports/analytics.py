"""Read-only analytics for dashboards and reports.

All numbers come from stored rows (metric snapshots, orders, payouts), never from live API calls,
so dashboards are fast and every figure can be traced back to its source row.
Brand-facing functions only ever read brand prices; creator-facing ones only creator fees.
"""

from datetime import timedelta

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from apps.content.models import Asset, Post
from apps.offers.models import Slot
from apps.payments.models import Order, Payout

LIVE_STATES = [Post.Status.LIVE, Post.Status.VERIFIED, Post.Status.MISSING]


def _latest_by_day(snapshots, days):
    """[(day, value_dict | None)] with each day's last snapshot at or before the end of that day."""
    snaps = sorted(snapshots, key=lambda s: s.captured_at)
    out, i, last = [], 0, None
    for day in days:
        end = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.max.time()))
        while i < len(snaps) and snaps[i].captured_at <= end:
            last = snaps[i]
            i += 1
        out.append((day, last))
    return out


def day_range(days):
    today = timezone.localdate()
    return [today - timedelta(days=n) for n in range(days - 1, -1, -1)]


def totals(posts, spend):
    t = {"posts": 0, "reach": 0, "views": 0, "engagements": 0, "spend": spend}
    for post in posts:
        t["posts"] += 1
        latest = post.snapshots.first()
        if latest:
            t["reach"] += latest.reach
            t["views"] += latest.views
            t["engagements"] += latest.engagements
    t["er"] = round(t["engagements"] / t["reach"] * 100, 1) if t["reach"] else None
    t["cpm"] = round(spend / t["views"] * 1000) if t["views"] and spend else None
    return t


def brand_posts(brand, campaign=None):
    qs = Post.objects.filter(slot__campaign__brand=brand, status__in=LIVE_STATES)
    if campaign is not None:
        qs = qs.filter(slot__campaign=campaign)
    return qs.select_related("slot__creator", "slot__campaign").prefetch_related("snapshots")


def brand_spend(brand, campaign=None):
    """Paid order value minus refunds (excl. GST)."""
    from apps.payments.models import Refund

    qs = Order.objects.filter(brand=brand, status=Order.Status.PAID)
    refunds = Refund.objects.filter(order__brand=brand).exclude(status=Refund.Status.FAILED)
    if campaign is not None:
        qs = qs.filter(campaign=campaign)
        refunds = refunds.filter(order__campaign=campaign)
    paid = qs.aggregate(t=Sum("subtotal"))["t"] or 0
    return paid - (refunds.aggregate(t=Sum("amount"))["t"] or 0)


def brand_overview(brand):
    posts = list(brand_posts(brand))
    return totals(posts, brand_spend(brand))


def views_over_time(posts, days=30):
    """Single series: total cumulative views across posts, per day."""
    day_list = day_range(days)
    per_post = [_latest_by_day(p.snapshots.all(), day_list) for p in posts]
    points = []
    for idx, day in enumerate(day_list):
        points.append({"x": day.isoformat(), "y": sum(pp[idx][1].views for pp in per_post if pp[idx][1])})
    return {"series": [{"name": "Views", "points": points}], "unit": "views"}


def views_per_post(posts, days=30, limit=8):
    """One series per post (max 8, matching the categorical palette); older days before a post
    was published are left empty rather than drawn as zero."""
    day_list = day_range(days)
    series = []
    ranked = sorted(
        posts, key=lambda p: p.snapshots.first().views if p.snapshots.first() else 0, reverse=True
    )
    for post in ranked[:limit]:
        pts = []
        for day, snap in _latest_by_day(post.snapshots.all(), day_list):
            pts.append({"x": day.isoformat(), "y": snap.views if snap else None})
        series.append({"name": f"@{post.slot.creator.ig_username}", "points": pts})
    return {"series": series, "unit": "views", "truncated": len(ranked) > limit}


def creator_rows(campaign):
    """Per-creator results for the brand: expected vs actual, brand prices only."""
    rows = []
    slots = campaign.slots.filter(creator__isnull=False).select_related("creator").order_by("position")
    posts = {p.slot_id: p for p in brand_posts(campaign.brand, campaign)}
    for slot in slots:
        if slot.status not in (*Slot.IN_PROGRESS, Slot.Status.VERIFIED):
            continue
        post = posts.get(slot.pk)
        latest = post.snapshots.first() if post else None
        row = {
            "creator": slot.creator.display_name,
            "handle": slot.creator.ig_username,
            "status": slot.get_status_display(),
            "price": slot.brand_price,
            "expected_reach": slot.creator.avg_reach,
            "reach": latest.reach if latest else None,
            "views": latest.views if latest else None,
            "engagements": latest.engagements if latest else None,
            "permalink": post.permalink if post else "",
        }
        row["er"] = round(latest.engagements / latest.reach * 100, 1) if latest and latest.reach else None
        row["cpm"] = round(slot.brand_price / latest.views * 1000) if latest and latest.views else None
        if latest and row["expected_reach"]:
            row["vs_expected"] = round((latest.reach - row["expected_reach"]) / row["expected_reach"] * 100)
        else:
            row["vs_expected"] = None
        rows.append(row)
    return rows


def upcoming_posts(brand, days=14):
    now = timezone.now()
    return (
        Post.objects.filter(
            slot__campaign__brand=brand,
            status__in=[Post.Status.SCHEDULED, Post.Status.AWAITING_SELF_POST],
            scheduled_for__lte=now + timedelta(days=days),
        )
        .select_related("slot__creator", "slot__campaign")
        .order_by("scheduled_for")
    )


def content_library(brand):
    """Approved, published content with the reuse window from each campaign's order."""
    now = timezone.now()
    items = []
    assets = (
        Asset.objects.filter(slot__campaign__brand=brand, status=Asset.Status.FINAL)
        .select_related("slot__creator", "slot__campaign", "slot__post")
        .order_by("-created_at")
    )
    for asset in assets:
        post = getattr(asset.slot, "post", None)
        published = post.published_at if post else None
        until = published + timedelta(days=asset.slot.campaign.usage_rights_days) if published else None
        days_left = (until - now).days if until else None
        items.append(
            {
                "asset": asset,
                "campaign": asset.slot.campaign,
                "creator": asset.slot.creator,
                "permalink": post.permalink if post else "",
                "published": published,
                "until": until,
                "days_left": days_left,
                "paid_ads": asset.slot.campaign.paid_ads_allowed,
                "state": "not_live"
                if until is None
                else ("expired" if days_left < 0 else ("expiring" if days_left <= 14 else "active")),
            }
        )
    return items


def weekly_summary(brand, since):
    """What changed for a brand in the last week (for the email digest)."""
    posts = list(brand_posts(brand))
    new_posts = [p for p in posts if p.published_at and p.published_at >= since]
    views_now = views_then = reach_now = 0
    for post in posts:
        snaps = list(post.snapshots.all())
        if not snaps:
            continue
        views_now += snaps[0].views
        reach_now += snaps[0].reach
        before = next((s for s in snaps if s.captured_at < since), None)
        views_then += before.views if before else 0
    in_review = Slot.objects.filter(campaign__brand=brand, status=Slot.Status.IN_REVIEW).count()
    return {
        "new_posts": new_posts,
        "views_gained": max(0, views_now - views_then),
        "total_views": views_now,
        "total_reach": reach_now,
        "in_review": in_review,
        "active_campaigns": brand.campaigns.filter(status__in=["offers_out", "active"]).count(),
    }


# --- Creator side ---------------------------------------------------------------------------


def financial_year(day):
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def fy_bounds(fy):
    start = int(fy[:4])
    return timezone.datetime(start, 4, 1).date(), timezone.datetime(start + 1, 3, 31).date()


def creator_payouts(creator):
    return (
        Payout.objects.filter(creator=creator).select_related("slot__campaign__brand").order_by("-created_at")
    )


def monthly_earnings(creator, months=6):
    """Net paid per month (single series), oldest first."""
    today = timezone.localdate().replace(day=1)
    buckets = []
    for n in range(months - 1, -1, -1):
        y, m = today.year, today.month - n
        while m <= 0:
            m += 12
            y -= 1
        buckets.append((y, m))
    paid = Payout.objects.filter(creator=creator, status=Payout.Status.PAID, paid_at__isnull=False)
    points = []
    for y, m in buckets:
        total = paid.filter(paid_at__year=y, paid_at__month=m).aggregate(t=Sum("net"))["t"] or 0
        points.append({"x": f"{y}-{m:02d}", "y": total / 100})
    return {"series": [{"name": "Paid to you (₹)", "points": points}], "unit": "₹"}


def fy_statement(creator, fy):
    """Payments in a financial year with a quarterly TDS summary."""
    start, end = fy_bounds(fy)
    payouts = list(
        Payout.objects.filter(
            creator=creator, status=Payout.Status.PAID, paid_at__date__gte=start, paid_at__date__lte=end
        )
        .select_related("slot__campaign__brand")
        .order_by("paid_at")
    )
    quarters = {q: {"gross": 0, "gst": 0, "tds": 0, "net": 0, "count": 0} for q in ("Q1", "Q2", "Q3", "Q4")}
    for p in payouts:
        month = timezone.localtime(p.paid_at).month
        q = (
            "Q1"
            if month in (4, 5, 6)
            else "Q2"
            if month in (7, 8, 9)
            else "Q3"
            if month in (10, 11, 12)
            else "Q4"
        )
        for key in ("gross", "gst", "tds", "net"):
            quarters[q][key] += getattr(p, key)
        quarters[q]["count"] += 1
    total = {k: sum(q[k] for q in quarters.values()) for k in ("gross", "gst", "tds", "net", "count")}
    return {
        "fy": fy,
        "start": start,
        "end": end,
        "payouts": payouts,
        "quarters": quarters,
        "total": total,
        "platform": settings,
    }


def creator_posts(creator):
    posts = (
        Post.objects.filter(slot__creator=creator, status__in=LIVE_STATES)
        .select_related("slot__campaign__brand")
        .prefetch_related("snapshots")
        .order_by("-published_at")
    )
    rows = []
    for post in posts:
        latest = post.snapshots.first()
        rows.append(
            {
                "post": post,
                "brand": post.slot.campaign.brand.company_name,
                "reach": latest.reach if latest else None,
                "views": latest.views if latest else None,
                "engagements": latest.engagements if latest else None,
                "vs_usual": round((latest.reach - creator.avg_reach) / creator.avg_reach * 100)
                if latest and creator.avg_reach
                else None,
            }
        )
    return rows


def as_table(chart):
    """Table view of a chart's data (headers, rows), so every value is readable without hover."""
    series = chart["series"]
    headers = ["Date"] + [s["name"] for s in series]
    rows = []
    for i, point in enumerate(series[0]["points"] if series else []):
        rows.append([point["x"]] + [s["points"][i]["y"] for s in series])
    return {"headers": headers, "rows": rows}
