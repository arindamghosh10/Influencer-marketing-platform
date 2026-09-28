import logging

from celery import shared_task

from . import services

log = logging.getLogger(__name__)


@shared_task
def process_deadlines():
    result = services.process_deadlines()
    if any(result.values()):
        log.info("Deadlines processed: %s", result)
    return result
