from django.core.management.base import BaseCommand

from apps.niches.services import load_taxonomy


class Command(BaseCommand):
    help = "Create or update the niche taxonomy (idempotent)."

    def handle(self, *args, **options):
        top, sub = load_taxonomy()
        self.stdout.write(self.style.SUCCESS(f"Loaded {top} categories and {sub} sub-niches."))
