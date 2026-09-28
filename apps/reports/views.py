from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.brands.views import get_brand
from apps.campaigns.models import Campaign
from apps.core.permissions import brand_required, creator_required
from apps.creators.models import CreatorProfile
from apps.payments.models import Order

from . import analytics


def _brand_or_setup(request):
    brand = get_brand(request)
    if brand is None:
        return None, redirect("brands:profile")
    return brand, None


@brand_required
def library(request):
    brand, redirect_ = _brand_or_setup(request)
    if redirect_:
        return redirect_
    items = analytics.content_library(brand)
    return render(
        request,
        "reports/library.html",
        {
            "items": items,
            "expiring": [i for i in items if i["state"] == "expiring"],
        },
    )


@brand_required
def billing(request):
    brand, redirect_ = _brand_or_setup(request)
    if redirect_:
        return redirect_
    from apps.payments.models import Refund

    orders = Order.objects.filter(brand=brand, status=Order.Status.PAID).select_related("campaign")
    refunds = (
        Refund.objects.filter(order__brand=brand)
        .exclude(status=Refund.Status.FAILED)
        .select_related("order__campaign")
    )
    totals = {
        "subtotal": sum(o.subtotal for o in orders) - sum(r.amount for r in refunds),
        "gst": sum(o.gst_total for o in orders) - sum(r.gst_total for r in refunds),
        "total": sum(o.total for o in orders) - sum(r.total for r in refunds),
    }
    return render(request, "reports/billing.html", {"orders": orders, "refunds": refunds, "totals": totals})


@brand_required
def campaign_report(request, pk):
    brand, redirect_ = _brand_or_setup(request)
    if redirect_:
        return redirect_
    campaign = get_object_or_404(Campaign, pk=pk, brand=brand)
    posts = list(analytics.brand_posts(brand, campaign))
    rows = analytics.creator_rows(campaign)
    with_views = [r for r in rows if r["views"]]
    context = {
        "campaign": campaign,
        "brief": campaign.confirmed_brief.data if campaign.confirmed_brief else {},
        "totals": analytics.totals(posts, analytics.brand_spend(brand, campaign)),
        "rows": rows,
        "best_er": max((r for r in with_views if r["er"] is not None), key=lambda r: r["er"], default=None),
        "best_cpm": min((r for r in with_views if r["cpm"]), key=lambda r: r["cpm"], default=None),
        "generated": timezone.now(),
    }
    return render(request, "reports/campaign_report.html", context)


def _creator(request):
    return get_object_or_404(CreatorProfile, user=request.user)


@creator_required
def earnings(request):
    creator = _creator(request)
    chart = analytics.monthly_earnings(creator)
    payouts = analytics.creator_payouts(creator)
    years = sorted(
        {analytics.financial_year(timezone.localtime(p.paid_at).date()) for p in payouts if p.paid_at}
        | {analytics.financial_year(timezone.localdate())},
        reverse=True,
    )
    from apps.payments.services import creator_earnings

    return render(
        request,
        "reports/earnings.html",
        {
            "creator": creator,
            "payouts": payouts,
            "chart": chart,
            "table": analytics.as_table(chart),
            "summary": creator_earnings(creator),
            "years": years,
            "posts": analytics.creator_posts(creator),
        },
    )


@creator_required
def statement(request, fy):
    creator = _creator(request)
    if len(fy) != 7 or not fy[:4].isdigit():
        return redirect("reports:earnings")
    return render(
        request, "reports/statement.html", {"creator": creator, **analytics.fy_statement(creator, fy)}
    )
