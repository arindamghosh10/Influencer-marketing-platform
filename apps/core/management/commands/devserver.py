"""One command to run the whole app locally:

    uv run python manage.py devserver

Sets up the database, loads demo data the first time, builds the stylesheet if it can,
starts the background scheduler and the web server on http://127.0.0.1:8000.
"""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.core.scheduler import start_in_background


class Command(BaseCommand):
    help = "Set up and run the app locally (database, demo data, styles, scheduler, web server)."

    def add_arguments(self, parser):
        parser.add_argument("addrport", nargs="?", default="127.0.0.1:8000")
        parser.add_argument("--no-demo", action="store_true", help="Don't load demo data")
        parser.add_argument("--interval", type=int, default=60, help="Scheduler interval in seconds")
        parser.add_argument(
            "--build-css",
            action="store_true",
            help="Rebuild the stylesheet after changing templates (downloads the Tailwind tool once)",
        )

    def handle(self, *args, **options):
        # Django's auto-reloader runs this command twice: once as a watcher and once (RUN_MAIN)
        # as the real server. Set-up runs once in the watcher; the scheduler runs in the server.
        if os.environ.get("RUN_MAIN") != "true":
            self._setup(options)
        else:
            start_in_background(options["interval"])
        call_command("runserver", options["addrport"])

    def _setup(self, options):
        if not settings.DEBUG:
            self.stdout.write(self.style.WARNING("DEBUG is off. For local use set DEBUG=true in .env."))
        self.stdout.write("Applying database migrations…")
        call_command("migrate", verbosity=0)
        if not options["no_demo"] and not get_user_model().objects.exists():
            self.stdout.write("Loading demo data (first run only)…")
            call_command("seed_demo", verbosity=0)
        if options["build_css"]:
            try:
                call_command("tailwind", "build", verbosity=0)
            except Exception as exc:  # offline or blocked: the committed stylesheet still works
                self.stdout.write(
                    self.style.WARNING(f"Stylesheet build failed ({exc}); using the included one.")
                )
        address = options["addrport"] if ":" in options["addrport"] else f"127.0.0.1:{options['addrport']}"
        self.stdout.write(
            self.style.SUCCESS(
                f"\nReady! Open http://{address}\n"
                "  Brand:   brand@demo.local\n"
                "  Creator: creator000@demo.local\n"
                "  Ops:     ops@demo.local   (admin at /admin/)\n"
                "  Password for all: demo-pass-123\n"
                "Emails (like signing codes) are printed in this terminal.\n"
            )
        )
