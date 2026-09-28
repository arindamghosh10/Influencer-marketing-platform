from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.content import services as content
from apps.content.models import Asset, Post
from apps.disputes import services as disputes
from apps.disputes.models import Dispute
from apps.offers.models import Slot
from apps.payments.models import Payout, Refund
from apps.payments.refunds import RefundError, cancel_paid_slot, issue_refund
from apps.reports import analytics


def _draft(slot):
    upload = SimpleUploadedFile("d.mp4", b"\x00\x00\x00\x18ftypmp42 x", content_type="video/mp4")
    content.submit_draft(slot, slot.creator.user, upload, "#ad Paid partnership. Great gel!")


def _publish(slot, brand_user):
    _draft(slot)
    content.brand_review(slot, Asset.objects.get(slot=slot), brand_user, "approved")

    class Req:
        user = slot.creator.user
        META = {"REMOTE_ADDR": "127.0.0.1"}

    content.final_approve(slot, Req(), timezone.now(), auto_publish=True)
    content.run_due(timezone.now() + timedelta(minutes=1))
    return Post.objects.get(slot=slot)


@pytest.mark.django_db
def test_creator_withdraw_refunds_brand_with_credit_note(client, paid_slot, brand_user):
    before = paid_slot.creator.reliability_score
    client.force_login(paid_slot.creator.user)
    client.post(reverse("content:withdraw", args=[paid_slot.pk]), {"reason": "Fell ill"})
    paid_slot.refresh_from_db()
    paid_slot.creator.refresh_from_db()
    assert paid_slot.status == Slot.Status.CANCELLED
    assert paid_slot.creator.reliability_score < before
    assert Payout.objects.get(slot=paid_slot).status == Payout.Status.CANCELLED
    refund = Refund.objects.get(slot=paid_slot)
    assert refund.status == Refund.Status.PROCESSED
    assert refund.amount == paid_slot.brand_price and refund.total == refund.amount + refund.gst_total
    assert refund.credit_note_number.startswith("CB-CN/")
    # Spend drops by the refunded amount; billing and credit note pages show it.
    assert analytics.brand_spend(brand_user.brand_profile) == paid_slot.order.subtotal - refund.amount
    client.force_login(brand_user)
    assert refund.credit_note_number in client.get(reverse("reports:billing")).content.decode()
    note = client.get(reverse("payments:credit_note", args=[refund.pk])).content.decode()
    assert paid_slot.order.invoice_number in note


@pytest.mark.django_db
def test_cannot_cancel_after_approval_or_refund_twice(paid_slot, brand_user):
    _draft(paid_slot)
    content.brand_review(paid_slot, Asset.objects.get(slot=paid_slot), brand_user, "approved")
    with pytest.raises(RefundError):
        cancel_paid_slot(paid_slot, "too late")
    order = paid_slot.order
    issue_refund(order, order.subtotal, "full")
    with pytest.raises(RefundError):
        issue_refund(order, 100, "more")


@pytest.mark.django_db
def test_ops_admin_cancel_and_refund_action(client, paid_slot):
    from apps.accounts.models import User

    ops = User.objects.get(email="ops@demo.local")
    client.force_login(ops)
    client.post(
        reverse("admin:offers_slot_changelist"),
        {
            "action": "cancel_and_refund",
            "_selected_action": [paid_slot.pk],
            "reason": "Brand changed plans",
        },
    )
    paid_slot.refresh_from_db()
    assert paid_slot.status == Slot.Status.CANCELLED and Refund.objects.filter(slot=paid_slot).exists()


@pytest.mark.django_db
def test_open_dispute_holds_payout_then_pay_creator_releases(client, paid_slot, brand_user):
    post = _publish(paid_slot, brand_user)
    client.force_login(brand_user)
    client.post(
        reverse("disputes:brand_report", args=[paid_slot.campaign_id, paid_slot.pk]),
        {"category": "off_brief", "description": "The product isn't shown"},
    )
    dispute = Dispute.objects.get(slot=paid_slot)
    assert dispute.status == Dispute.Status.OPEN
    # A second report while one is open is refused.
    with pytest.raises(disputes.DisputeError):
        disputes.raise_dispute(paid_slot, brand_user, "brand", "other", "again")

    content.run_due(post.published_at + timedelta(days=8))
    paid_slot.refresh_from_db()
    assert paid_slot.status == Slot.Status.VERIFIED
    assert Payout.objects.get(slot=paid_slot).status == Payout.Status.HELD  # held by the dispute

    disputes.resolve(dispute, Dispute.Resolution.PAY_CREATOR, "Product is visible at 0:04.", brand_user)
    assert Payout.objects.get(slot=paid_slot).status == Payout.Status.RELEASABLE


@pytest.mark.django_db
def test_dispute_split_refund_reduces_creator_payout(paid_slot, brand_user):
    post = _publish(paid_slot, brand_user)
    content.run_due(post.published_at + timedelta(days=8))  # verified, payout releasable
    payout = Payout.objects.get(slot=paid_slot)
    payout.status = Payout.Status.HELD  # e.g. report came in before release
    payout.save()
    dispute = disputes.raise_dispute(
        paid_slot, paid_slot.creator.user, "creator", "scope", "Asked for 3 reels"
    )
    half = paid_slot.brand_price // 2
    disputes.resolve(
        dispute, Dispute.Resolution.SPLIT, "Half delivered as agreed.", brand_user, refund_amount=half
    )
    payout.refresh_from_db()
    assert payout.gross == round(paid_slot.creator_fee * 0.5)
    assert payout.status == Payout.Status.RELEASABLE
    assert Refund.objects.get(slot=paid_slot).amount == half


@pytest.mark.django_db
def test_dispute_full_refund_cancels_payout(paid_slot, brand_user):
    _publish(paid_slot, brand_user)
    dispute = disputes.raise_dispute(paid_slot, brand_user, "brand", "post_changed", "Deleted after a day")
    disputes.resolve(dispute, Dispute.Resolution.REFUND_FULL, "Post was deleted.", brand_user)
    paid_slot.refresh_from_db()
    assert paid_slot.status == Slot.Status.CANCELLED
    assert Payout.objects.get(slot=paid_slot).status == Payout.Status.CANCELLED
    assert Refund.objects.get(slot=paid_slot).amount == paid_slot.brand_price
    assert Post.objects.get(slot=paid_slot).next_check_at is None


@pytest.mark.django_db
def test_ops_evidence_pack_and_resolve_view(client, paid_slot, brand_user):
    from apps.accounts.models import User

    _publish(paid_slot, brand_user)
    dispute = disputes.raise_dispute(paid_slot, brand_user, "brand", "off_brief", "Wrong product shown")
    client.force_login(User.objects.get(email="ops@demo.local"))
    page = client.get(reverse("disputes:detail", args=[dispute.pk])).content.decode()
    assert "Wrong product shown" in page and "Drafts and feedback" in page and "Campaign timeline" in page
    assert "Open disputes (1)" in client.get(reverse("core:ops")).content.decode()
    client.post(
        reverse("disputes:detail", args=[dispute.pk]),
        {"resolution": "no_change", "note": "Content matches the brief."},
    )
    dispute.refresh_from_db()
    assert dispute.status == Dispute.Status.RESOLVED


@pytest.mark.django_db
def test_dispute_pages_are_protected(client, paid_slot, brand_user, creator_user):
    dispute = disputes.raise_dispute(paid_slot, brand_user, "brand", "other", "x")
    client.force_login(brand_user)
    assert client.get(reverse("disputes:detail", args=[dispute.pk])).status_code == 403
    client.force_login(creator_user)  # not this slot's creator
    resp = client.post(
        reverse("disputes:creator_report", args=[paid_slot.pk]), {"category": "other", "description": "x"}
    )
    assert resp.status_code == 404
