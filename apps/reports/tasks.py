from celery import shared_task

from .digest import send_weekly_reports


@shared_task
def weekly_reports():
    return send_weekly_reports()
