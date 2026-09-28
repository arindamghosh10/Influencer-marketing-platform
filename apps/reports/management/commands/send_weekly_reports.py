from django.core.management.base import BaseCommand

from apps.reports.digest import send_weekly_reports


class Command(BaseCommand):
    help = "Email the weekly summary to brands (once per brand per ISO week; safe to re-run)."

    def handle(self, *args, **options):
        sent = send_weekly_reports()
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} weekly report(s)."))
