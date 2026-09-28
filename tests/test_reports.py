from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.content import services as content
from apps.content.models import Asset, Post
from apps.core.money import format_inr
from apps.payments.models import Payout
from apps.reports import analytics
from apps.reports.digest import send_weekly_reports
from apps.reports.models import WeeklyReportLog


def _publish(slot, rf_user):
    """Drive a paid slot to a live post using the real services."""
    upload = SimpleUploadedFile("d.mp4", b"\x00\x00\x00\x18ftypmp42 x", content_type="video/mp4")
    content.submit_draft(slot, slot.creator.user, upload, "#ad Paid partnership. Great gel!")
    content.brand_review(slot, Asset.objects.get(slot=slot), rf_user, "approved")
    slot.refresh_from_db()

    class Req:
        user = slot.creator.user
        META = {"REMOTE_ADDR": "127.0.0.1"}

    content.final_approve(slot, Req(), timezone.now(), auto_publish=True)
    content.run_due(timezone.now() + timedelta(minutes=1))
    return Post.objects.get(slot=slot)


@pytest.mark.django_db
def test_brand_dashboard_campaign_and_report_show_real_numbers(client, paid_slot, brand_user):
    post = _publish(paid_slot, brand_user)
    snap = post.snapshots.first()
    client.force_login(brand_user)

    home = client.get(reverse("brands:dashboard")).content.decode()
    assert "Views across all campaigns" in home and 'id="views-chart"' in home
    assert format_inr(paid_slot.order.subtotal) in home  # spend tile

    detail = client.get(reverse("campaigns:detail", args=[paid_slot.campaign_id])).content.decode()
    assert "Views per creator" in detail and "Results by creator" in detail
    assert format_inr(paid_slot.creator_fee) not in detail or paid_slot.creator_fee == paid_slot.brand_price

    report = client.get(reverse("reports:campaign_report", args=[paid_slot.campaign_id])).content.decode()
    assert f"@{paid_slot.creator.ig_username}" in report
    rows = analytics.creator_rows(paid_slot.campaign)
    assert rows[0]["views"] == snap.views and rows[0]["price"] == paid_slot.brand_price
    assert rows[0]["cpm"] == round(paid_slot.brand_price / snap.views * 1000)


@pytest.mark.django_db
def test_views_over_time_is_cumulative_and_per_day(paid_slot, brand_user):
    post = _publish(paid_slot, brand_user)
    chart = analytics.views_over_time([post], days=7)
    points = chart["series"][0]["points"]
    assert len(points) == 7 and points[-1]["y"] == post.snapshots.first().views
    table = analytics.as_table(chart)
    assert table["headers"] == ["Date", "Views"] and len(table["rows"]) == 7


@pytest.mark.django_db
def test_content_library_usage_window(client, paid_slot, brand_user):
    post = _publish(paid_slot, brand_user)
    items = analytics.content_library(brand_user.brand_profile)
    assert len(items) == 1 and items[0]["state"] == "active"
    assert items[0]["until"].date() == (post.published_at + timedelta(days=90)).date()
    Post.objects.filter(pk=post.pk).update(published_at=timezone.now() - timedelta(days=80))
    assert analytics.content_library(brand_user.brand_profile)[0]["state"] == "expiring"
    client.force_login(brand_user)
    page = client.get(reverse("reports:library")).content.decode()
    assert "Reuse until" in page and "Paid ads allowed" in page


@pytest.mark.django_db
def test_billing_lists_paid_invoices(client, paid_slot, brand_user):
    client.force_login(brand_user)
    page = client.get(reverse("reports:billing")).content.decode()
    assert paid_slot.order.invoice_number in page


@pytest.mark.django_db
def test_weekly_report_sent_once_per_week(paid_slot, brand_user):
    _publish(paid_slot, brand_user)
    mail.outbox.clear()
    assert send_weekly_reports() == 1
    assert "new views" in mail.outbox[-1].subject
    assert mail.outbox[-1].alternatives  # HTML version
    assert send_weekly_reports() == 0  # same ISO week: not sent again
    assert WeeklyReportLog.objects.count() == 1


@pytest.mark.django_db
def test_creator_earnings_and_statement(client, paid_slot, brand_user):
    post = _publish(paid_slot, brand_user)
    content.run_due(post.published_at + timedelta(days=8))
    payout = Payout.objects.get(slot=paid_slot)
    assert payout.status == Payout.Status.RELEASABLE
    payout.status, payout.utr, payout.paid_at = Payout.Status.PAID, "UTR123456", timezone.now()
    payout.save()

    client.force_login(paid_slot.creator.user)
    page = client.get(reverse("reports:earnings")).content.decode()
    assert "UTR123456" in page and format_inr(payout.net) in page
    assert format_inr(paid_slot.brand_price) not in page  # creators never see the brand price

    fy = analytics.financial_year(timezone.localdate())
    statement = client.get(reverse("reports:statement", args=[fy])).content.decode()
    assert f"FY {fy}" in statement and format_inr(payout.tds) in statement
    data = analytics.fy_statement(paid_slot.creator, fy)
    assert data["total"]["net"] == payout.net and data["total"]["count"] == 1


def test_financial_year_boundaries():
    from datetime import date

    assert analytics.financial_year(date(2026, 3, 31)) == "2025-26"
    assert analytics.financial_year(date(2026, 4, 1)) == "2026-27"


@pytest.mark.django_db
def test_reports_are_role_protected(client, paid_slot, brand_user, creator_user):
    client.force_login(creator_user)
    assert client.get(reverse("reports:library")).status_code == 403
    client.force_login(brand_user)
    assert client.get(reverse("reports:earnings")).status_code == 403
