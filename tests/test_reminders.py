from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.content import services as content
from apps.content.models import Asset
from apps.offers import services as offers
from apps.offers.models import Offer, Slot
from apps.offers.reminders import send_reminders
from apps.payments.services import start_order
from tests.test_offers_payments import _send, shortlisted  # noqa: F401


@pytest.mark.django_db
def test_offer_and_payment_reminders_sent_once(client, shortlisted, brand_user, settings):  # noqa: F811
    settings.SITE_URL = "https://app.example.in"
    offer, other = _send(client, shortlisted)
    now = timezone.now()
    assert send_reminders(now) == 0  # 48h left: too early
    later = offer.expires_at - timedelta(hours=6)
    assert send_reminders(later) == 2  # both pending offers
    assert send_reminders(later) == 0
    note = offer.creator.user.notifications.first()
    assert "expires in 6" in note.title
    emails = " ".join(m.body for m in mail.outbox)
    assert f"https://app.example.in/creator/offers/{offer.pk}/" in emails  # absolute link in email

    offers.accept(offer, agreement=None)
    offer.slot.refresh_from_db()
    due = offer.slot.payment_due_at
    assert send_reminders(due - timedelta(hours=30)) == 0
    assert send_reminders(due - timedelta(hours=10)) == 1
    assert brand_user.notifications.filter(title__startswith="Pay within").count() == 1
    # Paying stops further reminders for that slot.
    start_order(shortlisted)


@pytest.mark.django_db
def test_review_and_final_ok_reminders(paid_slot, brand_user):
    upload = SimpleUploadedFile("d.mp4", b"\x00\x00\x00\x18ftypmp42 x", content_type="video/mp4")
    content.submit_draft(paid_slot, paid_slot.creator.user, upload, "#ad Paid partnership. Great gel!")
    paid_slot.refresh_from_db()
    assert send_reminders(paid_slot.review_due_at - timedelta(hours=5)) == 1
    assert brand_user.notifications.filter(title__contains="approved automatically").exists()

    content.brand_review(paid_slot, Asset.objects.get(slot=paid_slot), brand_user, "approved")
    paid_slot.refresh_from_db()
    assert paid_slot.status == Slot.Status.APPROVED
    assert send_reminders(timezone.now() + timedelta(hours=2)) == 0
    assert send_reminders(timezone.now() + timedelta(hours=25)) == 1
    assert paid_slot.creator.user.notifications.filter(title__contains="approved your draft").exists()


@pytest.mark.django_db
def test_draft_deadline_reminder(paid_slot):
    campaign = paid_slot.campaign
    campaign.content_deadline = timezone.localdate() + timedelta(days=5)
    campaign.save()
    assert send_reminders(timezone.now()) == 0
    assert send_reminders(timezone.now() + timedelta(days=4)) == 1
    assert Offer.objects.filter(slot=paid_slot).exists()
