import hashlib
import hmac
import json
import re
from datetime import timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.campaigns.models import Campaign
from apps.contracts.models import Agreement, AgreementKind, ConsentEvent
from apps.core.money import format_inr
from apps.matching.models import MatchCandidate
from apps.offers import services as offers
from apps.offers.models import Offer, Slot
from apps.payments.models import Order, Payout, WebhookEvent
from apps.payments.tax import gst_split, payout_breakdown


def _sign(client, name="Signer"):
    resp = client.post(reverse("contracts:sign"), {"signed_name": name, "accept": "on"})
    assert resp.status_code == 302, resp
    code = re.search(r"\b(\d{6})\b", mail.outbox[-1].subject).group(1)
    return client.post(reverse("contracts:verify"), {"code": code})


@pytest.fixture
def shortlisted(client, seeded, brand_user):
    """A campaign with a confirmed brief and 2 creators selected."""
    client.force_login(brand_user)
    client.post(
        reverse("campaigns:create"),
        {
            "title": "Sunscreen launch",
            "product_notes": "SunShield SPF 50 gel sunscreen for oily skin.",
            "objective": "awareness",
            "deliverable": "reel",
            "budget_rupees": 300000,
            "creators_wanted": 2,
            "target_gender": "any",
            "content_mode": "creator_made",
            "usage_rights_days": 90,
            "paid_ads_allowed": "on",
        },
    )
    campaign = Campaign.objects.get(title="Sunscreen launch")
    client.post(reverse("campaigns:confirm_brief", args=[campaign.pk]), {"claims_ack": "1"})
    client.post(reverse("campaigns:confirm_selection", args=[campaign.pk]))
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.SHORTLISTED
    run = campaign.match_runs.first()
    assert run.candidates.filter(selected=True).count() == 2
    assert run.candidates.filter(role=MatchCandidate.Role.BACKUP).exists()
    return campaign


def _send(client, campaign):
    client.post(reverse("campaigns:send_offers", args=[campaign.pk]))
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.OFFERS_OUT
    return list(Offer.objects.filter(slot__campaign=campaign, status=Offer.Status.PENDING))


def _accept_as_creator(client, offer):
    client.force_login(offer.creator.user)
    resp = client.post(reverse("offers:accept", args=[offer.pk]))
    assert resp.url == reverse("contracts:sign")
    resp = _sign(client, offer.creator.display_name)
    assert resp.url == reverse("offers:complete", args=[offer.pk])
    client.get(resp.url)
    offer.refresh_from_db()
    return offer


@pytest.mark.django_db
def test_unapproved_brand_cannot_send_offers(client, shortlisted, brand_user):
    brand = brand_user.brand_profile
    brand.status = brand.Status.PENDING_REVIEW
    brand.save()
    client.post(reverse("campaigns:send_offers", args=[shortlisted.pk]))
    shortlisted.refresh_from_db()
    assert shortlisted.status == Campaign.Status.SHORTLISTED
    assert not Offer.objects.exists()


@pytest.mark.django_db
def test_offer_accept_pay_flow(client, shortlisted, brand_user):
    pending = _send(client, shortlisted)
    assert len(pending) == 2
    assert any("New offer" in m.subject for m in mail.outbox)

    offer = pending[0]
    # Creator sees their fee and never the brand price.
    client.force_login(offer.creator.user)
    page = client.get(reverse("offers:detail", args=[offer.pk])).content.decode()
    assert format_inr(offer.creator_fee) in page
    assert format_inr(offer.brand_price) not in page

    offer = _accept_as_creator(client, offer)
    assert offer.status == Offer.Status.ACCEPTED
    agreement = offer.agreement
    assert agreement.kind == AgreementKind.CREATOR_CAMPAIGN and agreement.campaign == shortlisted
    assert format_inr(offer.creator_fee) in agreement.body
    assert format_inr(offer.brand_price) not in agreement.body
    assert ConsentEvent.objects.filter(user=offer.creator.user, scope="paid_ads_usage", campaign=shortlisted)
    slot = offer.slot
    slot.refresh_from_db()
    assert slot.status == Slot.Status.ACCEPTED and slot.payment_due_at

    # Brand pays for the accepted creator only.
    client.force_login(brand_user)
    detail = client.get(reverse("campaigns:detail", args=[shortlisted.pk])).content.decode()
    assert "Ready to pay" in detail
    resp = client.post(reverse("payments:start", args=[shortlisted.pk]))
    assert resp.url == reverse("contracts:sign")
    order = Order.objects.get(campaign=shortlisted)
    assert order.subtotal == slot.brand_price
    assert order.total == order.subtotal + order.gst_total
    resp = _sign(client)
    assert resp.url == reverse("payments:checkout", args=[order.pk])
    page = client.get(resp.url).content.decode()
    order.refresh_from_db()
    assert order.status == Order.Status.CREATED and order.provider == "mock"
    assert Agreement.objects.get(pk=order.agreement_id).kind == AgreementKind.BRAND_ORDER
    assert format_inr(slot.creator_fee) not in page or slot.creator_fee == slot.brand_price

    client.post(reverse("payments:confirm", args=[order.pk]), {"mock_confirm": order.provider_order_id})
    order.refresh_from_db()
    slot.refresh_from_db()
    shortlisted.refresh_from_db()
    assert order.status == Order.Status.PAID and order.invoice_number.startswith("CB/")
    assert slot.status == Slot.Status.CONFIRMED
    assert shortlisted.status == Campaign.Status.ACTIVE
    payout = Payout.objects.get(slot=slot)
    assert payout.status == Payout.Status.HELD and payout.gross == slot.creator_fee
    assert payout.net == payout.gross + payout.gst - payout.tds

    invoice = client.get(reverse("payments:invoice", args=[order.pk])).content.decode()
    assert order.invoice_number in invoice and format_inr(order.total) in invoice

    # Paying twice is harmless.
    from apps.payments.services import mark_paid

    mark_paid(order.pk, "again")
    assert Payout.objects.filter(slot=slot).count() == 1


@pytest.mark.django_db
def test_wrong_mock_confirmation_is_rejected(client, shortlisted, brand_user):
    offer = _send(client, shortlisted)[0]
    _accept_as_creator(client, offer)
    client.force_login(brand_user)
    client.post(reverse("payments:start", args=[shortlisted.pk]))
    _sign(client)
    order = Order.objects.get(campaign=shortlisted)
    client.get(reverse("payments:checkout", args=[order.pk]))
    client.post(reverse("payments:confirm", args=[order.pk]), {"mock_confirm": "forged"})
    order.refresh_from_db()
    assert order.status == Order.Status.CREATED


@pytest.mark.django_db
def test_decline_offers_next_backup(client, shortlisted):
    offer = _send(client, shortlisted)[0]
    client.force_login(offer.creator.user)
    client.post(reverse("offers:decline", args=[offer.pk]), {"reason": "timing"})
    offer.refresh_from_db()
    assert offer.status == Offer.Status.DECLINED
    replacement = offer.slot.current_offer
    assert replacement.pk != offer.pk and replacement.status == Offer.Status.PENDING
    assert replacement.candidate.role == MatchCandidate.Role.BACKUP
    assert replacement.creator != offer.creator


@pytest.mark.django_db
def test_expired_offer_moves_to_backup_and_lowers_reliability(client, shortlisted):
    offer = _send(client, shortlisted)[0]
    before = offer.creator.reliability_score
    result = offers.process_deadlines(now=timezone.now() + timedelta(hours=49))
    assert result["expired_offers"] == 2
    offer.refresh_from_db()
    offer.creator.refresh_from_db()
    assert offer.status == Offer.Status.EXPIRED
    assert offer.creator.reliability_score < before
    assert offer.slot.current_offer.status == Offer.Status.PENDING


@pytest.mark.django_db
def test_slot_unfilled_when_backups_run_out(client, shortlisted):
    run = shortlisted.match_runs.first()
    run.candidates.filter(role=MatchCandidate.Role.BACKUP).delete()
    offer = _send(client, shortlisted)[0]
    offers.decline(offer, "busy")
    offer.slot.refresh_from_db()
    assert offer.slot.status == Slot.Status.UNFILLED


@pytest.mark.django_db
def test_backup_must_fit_remaining_budget(client, shortlisted):
    offer = _send(client, shortlisted)[0]
    other = Offer.objects.filter(slot__campaign=shortlisted).exclude(pk=offer.pk).first()
    # Leave only a tiny budget for the replacement.
    shortlisted.budget = other.brand_price + 1
    shortlisted.save()
    offers.decline(offer, "fee")
    offer.slot.refresh_from_db()
    assert offer.slot.status == Slot.Status.UNFILLED


@pytest.mark.django_db
def test_unpaid_acceptance_is_released(client, shortlisted):
    offer = _accept_as_creator(client, _send(client, shortlisted)[0])
    result = offers.process_deadlines(now=timezone.now() + timedelta(hours=121))
    assert result["released_slots"] == 1
    offer.refresh_from_db()
    assert offer.status == Offer.Status.RELEASED
    assert offer.slot.status == Slot.Status.CANCELLED


@pytest.mark.django_db
def test_creator_cannot_open_someone_elses_offer(client, shortlisted, creator_user):
    offer = _send(client, shortlisted)[0]
    client.force_login(creator_user)
    assert client.get(reverse("offers:detail", args=[offer.pk])).status_code == 404


@pytest.mark.django_db
def test_razorpay_signature_and_webhook(client, settings, shortlisted, brand_user):
    from apps.payments.providers import PaymentError, RazorpayPayments
    from apps.payments.services import start_order

    settings.RAZORPAY_KEY_ID = "rzp_test_x"
    settings.RAZORPAY_KEY_SECRET = "secret"
    settings.RAZORPAY_WEBHOOK_SECRET = "hook-secret"
    offer = _accept_as_creator(client, _send(client, shortlisted)[0])
    order = start_order(shortlisted)
    order.provider = "razorpay"
    order.provider_order_id = "order_ABC"
    order.status = Order.Status.CREATED
    order.save()

    provider = RazorpayPayments()
    good = hmac.new(b"secret", b"order_ABC|pay_1", hashlib.sha256).hexdigest()
    assert (
        provider.verify_checkout(
            order,
            {"razorpay_order_id": "order_ABC", "razorpay_payment_id": "pay_1", "razorpay_signature": good},
        )
        == "pay_1"
    )
    with pytest.raises(PaymentError):
        provider.verify_checkout(
            order,
            {"razorpay_order_id": "order_ABC", "razorpay_payment_id": "pay_1", "razorpay_signature": "bad"},
        )

    body = json.dumps(
        {
            "event": "payment.captured",
            "payload": {
                "payment": {"entity": {"id": "pay_1", "order_id": "order_ABC", "amount": order.total}}
            },
        }
    ).encode()
    sig = hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
    url = reverse("payments:razorpay_webhook")
    assert (
        client.post(url, body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE="bad").status_code
        == 400
    )
    resp = client.post(
        url,
        body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=sig,
        HTTP_X_RAZORPAY_EVENT_ID="evt_1",
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.Status.PAID
    resp = client.post(
        url,
        body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=sig,
        HTTP_X_RAZORPAY_EVENT_ID="evt_1",
    )
    assert resp.content == b"duplicate"
    assert WebhookEvent.objects.count() == 1
    assert Payout.objects.filter(slot=offer.slot).count() == 1


@pytest.mark.django_db
def test_webhook_amount_mismatch_is_rejected(client, settings, shortlisted):
    from apps.payments.services import start_order

    settings.RAZORPAY_WEBHOOK_SECRET = "hook-secret"
    _accept_as_creator(client, _send(client, shortlisted)[0])
    order = start_order(shortlisted)
    order.provider, order.provider_order_id, order.status = "razorpay", "order_X", Order.Status.CREATED
    order.save()
    body = json.dumps(
        {
            "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": "pay_2", "order_id": "order_X", "amount": 100}}},
        }
    ).encode()
    sig = hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
    resp = client.post(
        reverse("payments:razorpay_webhook"),
        body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=sig,
        HTTP_X_RAZORPAY_EVENT_ID="evt_2",
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.Status.CREATED


def test_gst_split_by_state(settings):
    settings.PLATFORM_STATE_CODE = "27"
    intra = gst_split(1_000_000, "27AAPFU0939F1ZV")
    assert (intra.cgst, intra.sgst, intra.igst) == (90_000, 90_000, 0)
    inter = gst_split(1_000_000, "29AAGCB7383J1Z4")
    assert (inter.cgst, inter.sgst, inter.igst) == (0, 0, 180_000)


def test_tds_rate_by_pan_type(settings):
    from apps.creators.models import CreatorProfile

    individual = CreatorProfile(pan="ABCPE1234F")
    firm = CreatorProfile(pan="ABCFE1234F", gstin="27ABCFE1234F1Z5")
    b = payout_breakdown(individual, 500_000)
    assert (b.tds, b.gst, b.net) == (5_000, 0, 495_000)
    b = payout_breakdown(firm, 500_000)
    assert (b.tds, b.gst, b.net) == (10_000, 90_000, 580_000)


@pytest.mark.django_db
def test_invoice_numbers_are_sequential_per_financial_year():
    from datetime import date

    from apps.payments.models import InvoiceSequence

    assert InvoiceSequence.next_number(date(2026, 9, 1)) == "CB/2026-27/00001"
    assert InvoiceSequence.next_number(date(2027, 3, 31)) == "CB/2026-27/00002"
    assert InvoiceSequence.next_number(date(2027, 4, 1)) == "CB/2027-28/00001"
