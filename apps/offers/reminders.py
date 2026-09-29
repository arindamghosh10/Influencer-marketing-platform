"""Nudges before deadlines, so fewer offers expire and fewer slots get released.

Each reminder is sent once (tracked in SentReminder), in-app and by email.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils.timesince import timeuntil

from apps.core.events import notify
from apps.core.models import SentReminder

from .models import Offer, Slot

OFFER_WINDOW = timedelta(hours=12)
PAYMENT_WINDOW = timedelta(hours=24)
REVIEW_WINDOW = timedelta(hours=24)
FINAL_OK_AFTER = timedelta(hours=24)
DRAFT_DEADLINE_WINDOW = timedelta(days=2)


def _once(key):
    """True the first time a key is claimed."""
    try:
        with transaction.atomic():
            SentReminder.objects.create(key=key)
        return True
    except IntegrityError:
        return False


def send_reminders(now):
    sent = 0

    for offer in Offer.objects.filter(
        status=Offer.Status.PENDING, expires_at__gt=now, expires_at__lte=now + OFFER_WINDOW
    ).select_related("creator__user", "slot__campaign__brand"):
        if _once(f"offer:{offer.pk}:expiring"):
            notify(
                offer.creator.user,
                f"Your offer from {offer.slot.campaign.brand.company_name} expires in "
                f"{timeuntil(offer.expires_at, now)}",
                "Accept or decline so the brand can plan. If you don't reply, it goes to another creator.",
                url=reverse("offers:detail", args=[offer.pk]),
            )
            sent += 1

    for slot in Slot.objects.filter(
        status=Slot.Status.ACCEPTED, payment_due_at__gt=now, payment_due_at__lte=now + PAYMENT_WINDOW
    ).select_related("campaign__brand__user", "creator"):
        if _once(f"slot:{slot.pk}:payment:{slot.payment_due_at:%Y%m%d%H%M}"):
            notify(
                slot.campaign.brand.user,
                f"Pay within {timeuntil(slot.payment_due_at, now)} to keep {slot.creator.display_name}",
                f"{slot.creator.display_name} accepted '{slot.campaign.title}'. If payment isn't made in "
                "time, the slot is offered to your next backup creator.",
                url=reverse("campaigns:detail", args=[slot.campaign_id]),
            )
            sent += 1

    for slot in Slot.objects.filter(
        status=Slot.Status.IN_REVIEW, review_due_at__gt=now, review_due_at__lte=now + REVIEW_WINDOW
    ).select_related("campaign__brand__user", "creator"):
        if _once(f"slot:{slot.pk}:review:{slot.review_due_at:%Y%m%d%H%M}"):
            notify(
                slot.campaign.brand.user,
                f"Review {slot.creator.display_name}'s draft: it's approved automatically in "
                f"{timeuntil(slot.review_due_at, now)}",
                "Approve it or ask for changes before then.",
                url=reverse("content:review", args=[slot.campaign_id, slot.pk]),
            )
            sent += 1

    for slot in Slot.objects.filter(
        status=Slot.Status.APPROVED, updated_at__lte=now - FINAL_OK_AFTER
    ).select_related("creator__user", "campaign"):
        if _once(f"slot:{slot.pk}:final_ok"):
            notify(
                slot.creator.user,
                f"The brand approved your draft for '{slot.campaign.title}'",
                "Give your final OK and pick a posting time to get it live.",
                url=reverse("content:workspace", args=[slot.pk]),
            )
            sent += 1

    for slot in Slot.objects.filter(
        status__in=[Slot.Status.CONFIRMED, Slot.Status.CHANGES_REQUESTED],
        campaign__content_deadline__isnull=False,
        campaign__content_deadline__lte=(now + DRAFT_DEADLINE_WINDOW).date(),
    ).select_related("creator__user", "campaign"):
        if _once(f"slot:{slot.pk}:draft_deadline"):
            notify(
                slot.creator.user,
                f"Draft due {slot.campaign.content_deadline:%d %b} for '{slot.campaign.title}'",
                "Upload your draft so the brand has time to review it.",
                url=reverse("content:workspace", args=[slot.pk]),
            )
            sent += 1
    return sent
