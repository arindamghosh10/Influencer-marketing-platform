"""Weekly email digest for brands (Monday mornings)."""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.brands.models import BrandProfile

from . import analytics
from .models import WeeklyReportLog

log = logging.getLogger(__name__)


def iso_week(day):
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def send_weekly_reports(now=None):
    """Send each approved brand with campaign activity one digest per ISO week. Safe to re-run."""
    now = now or timezone.now()
    week = iso_week(timezone.localtime(now).date())
    since = now - timedelta(days=7)
    sent = 0
    brands = BrandProfile.objects.filter(status=BrandProfile.Status.APPROVED).select_related("user")
    for brand in brands:
        if not brand.campaigns.exclude(status__in=["draft", "cancelled"]).exists():
            continue
        try:
            with transaction.atomic():
                WeeklyReportLog.objects.create(brand=brand, week=week)
        except IntegrityError:
            continue  # already sent this week
        summary = analytics.weekly_summary(brand, since)
        context = {
            "brand": brand,
            "summary": summary,
            "overview": analytics.brand_overview(brand),
            "dashboard_url": settings.SITE_URL.rstrip("/") + reverse("brands:dashboard"),
            "platform_name": settings.PLATFORM_NAME,
            "week": week,
        }
        text = render_to_string("reports/email/weekly.txt", context)
        html = render_to_string("reports/email/weekly.html", context)
        message = EmailMultiAlternatives(
            f"Your week on {settings.PLATFORM_NAME}: {summary['views_gained']:,} new views",
            text,
            None,
            [brand.user.email],
        )
        message.attach_alternative(html, "text/html")
        try:
            message.send()
            sent += 1
        except Exception:  # SMTP errors: log and let next week's run try again
            log.exception("Weekly report to %s failed", brand.user.email)
            WeeklyReportLog.objects.filter(brand=brand, week=week).delete()
    return sent
