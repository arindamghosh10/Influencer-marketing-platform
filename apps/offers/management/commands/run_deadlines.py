from django.core.management.base import BaseCommand

from apps.offers.services import process_deadlines


class Command(BaseCommand):
    help = "Expire unanswered offers and release unpaid slots (also runs every 5 min via Celery Beat)."

    def handle(self, *args, **options):
        result = process_deadlines()
        self.stdout.write(self.style.SUCCESS(f"Done: {result}"))
