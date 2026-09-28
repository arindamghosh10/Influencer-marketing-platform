"""A tiny in-process scheduler for local development: no Redis or Celery needed.

In production, Celery Beat runs the same jobs (see CELERY_BEAT_SCHEDULE).
"""

import logging
import threading
import time

from django.db import close_old_connections
from django.utils import timezone

log = logging.getLogger("scheduler")


def run_once():
    from apps.offers.services import process_deadlines
    from apps.reports.digest import send_weekly_reports

    result = process_deadlines()
    if any(result.values()):
        log.info("Scheduled jobs: %s", result)
    now = timezone.localtime()
    if now.weekday() == 0 and now.hour >= 9:  # Monday from 09:00; sent once per ISO week
        sent = send_weekly_reports()
        if sent:
            log.info("Weekly reports sent: %s", sent)


def loop(interval, stop_event=None):
    log.info("Scheduler running every %ss (offers, reviews, publishing, verification, reports)", interval)
    while not (stop_event and stop_event.is_set()):
        close_old_connections()
        try:
            run_once()
        except Exception:  # keep the loop alive; the next run retries
            log.exception("Scheduled job failed")
        finally:
            close_old_connections()
        if stop_event:
            stop_event.wait(interval)
        else:
            time.sleep(interval)


def start_in_background(interval=60):
    thread = threading.Thread(target=loop, args=(interval,), name="scheduler", daemon=True)
    thread.start()
    return thread
