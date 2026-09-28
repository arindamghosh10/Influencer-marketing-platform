from django.core.management.base import BaseCommand

from apps.core.scheduler import loop


class Command(BaseCommand):
    help = "Run scheduled jobs in a loop (local alternative to Celery Beat). Ctrl+C to stop."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=60, help="Seconds between runs (default 60)")

    def handle(self, *args, **options):
        try:
            loop(options["interval"])
        except KeyboardInterrupt:
            self.stdout.write("Scheduler stopped.")
