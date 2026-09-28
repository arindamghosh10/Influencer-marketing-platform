"""Refunds to brands. Every refund gets a GST credit note number against the original invoice.

Refunds are only issued for work that won't be delivered: a paid creator who withdraws or is
removed before their content is approved, a creator released while the brand was paying, or a
dispute resolved in the brand's favour.
"""

import logging

from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from apps.core.events import notify, record
from apps.core.money import format_inr
from apps.integrations.registry import get_provider
from apps.offers.models import Slot

from .models import InvoiceSequence, Order, Payout, Refund
from .providers import PaymentError
from .tax import gst_split

log = logging.getLogger(__name__)

# A paid slot can only be cancelled with a refund before the brand approves the content.
REFUNDABLE_SLOT_STATES = (Slot.Status.CONFIRMED, Slot.Status.IN_REVIEW, Slot.Status.CHANGES_REQUESTED)


class RefundError(Exception):
    pass


def refunded_amount(order):
    return order.refunds.exclude(status=Refund.Status.FAILED).aggregate(t=Sum("amount"))["t"] or 0


def issue_refund(order, amount, reason, *, slot=None, actor=None):
    """Refund `amount` (taxable value, paise) plus its GST on a paid order."""
    if order.status != Order.Status.PAID:
        raise RefundError("Only paid orders can be refunded.")
    if amount <= 0:
        raise RefundError("Refund amount must be positive.")
    if refunded_amount(order) + amount > order.subtotal:
        raise RefundError("That's more than is left to refund on this order.")
    split = gst_split(amount, order.brand.gstin)
    refund = Refund.objects.create(
        order=order,
        slot=slot,
        amount=amount,
        cgst=split.cgst,
        sgst=split.sgst,
        igst=split.igst,
        total=amount + split.total,
        reason=reason[:300],
        credit_note_number=InvoiceSequence.next_number(timezone.localdate(), series="CN"),
        created_by=actor,
    )
    provider = get_provider("payments")
    try:
        refund.provider_refund_id, processed = provider.refund(order, refund.total, reason)
    except PaymentError as exc:
        refund.status = Refund.Status.FAILED
        refund.error = str(exc)[:300]
        refund.save(update_fields=["status", "error", "updated_at"])
        log.error("Refund %s failed: %s", refund.pk, exc)
        _notify_ops(refund, f"Refund failed: {exc}")
        return refund
    if processed:
        refund.status = Refund.Status.PROCESSED
        refund.processed_at = timezone.now()
    refund.save()
    record(
        "refund.issued",
        f"Refund {format_inr(refund.total)} ({refund.credit_note_number}): {reason}",
        actor=actor,
        target=order.campaign,
        data={"refund": refund.pk},
    )
    notify(
        order.brand.user,
        f"Refund of {format_inr(refund.total)} on its way",
        f"{reason}. Credit note {refund.credit_note_number}. Refunds reach your account in 5–7 working days.",
        url=reverse("payments:credit_note", args=[refund.pk]),
    )
    return refund


@transaction.atomic
def cancel_paid_slot(slot, reason, *, actor=None, by_creator=False):
    """Cancel a paid slot before its content is approved: cancel the payout, refund the brand."""
    slot = (
        Slot.objects.select_for_update(of=("self",))
        .select_related("campaign__brand__user", "creator__user")
        .get(pk=slot.pk)
    )
    if slot.status not in REFUNDABLE_SLOT_STATES:
        raise RefundError(
            "This creator's content is already approved or live, so it can't be cancelled here."
        )
    if slot.order is None or slot.order.status != Order.Status.PAID:
        raise RefundError("This slot hasn't been paid for.")
    payout = Payout.objects.filter(slot=slot).first()
    if payout and payout.status == Payout.Status.PAID:
        raise RefundError("The creator has already been paid for this slot.")
    if payout:
        payout.status = Payout.Status.CANCELLED
        payout.save(update_fields=["status", "updated_at"])
    slot.status = Slot.Status.CANCELLED
    slot.save(update_fields=["status", "updated_at"])
    if by_creator:
        creator = slot.creator
        creator.reliability_score = round(max(0.0, creator.reliability_score - 0.1), 3)
        creator.save(update_fields=["reliability_score", "updated_at"])
    record(
        "slot.cancelled_after_payment",
        f"{slot.creator.display_name}'s slot cancelled: {reason}",
        actor=actor,
        target=slot.campaign,
    )
    refund = issue_refund(slot.order, slot.brand_price, reason, slot=slot, actor=actor)
    notify(
        slot.campaign.brand.user,
        f"{slot.creator.display_name} won't be delivering",
        f"{reason}. We've refunded their price. You can add another creator from the campaign page.",
        url=reverse("campaigns:detail", args=[slot.campaign_id]),
    )
    if not by_creator:
        notify(slot.creator.user, f"Campaign cancelled: {slot.campaign.title}", reason)
    from apps.content.services import maybe_complete_campaign

    maybe_complete_campaign(slot.campaign)
    return refund


def mark_refund_status(provider_refund_id, processed, error=""):
    refund = Refund.objects.filter(provider_refund_id=provider_refund_id).first()
    if refund is None or refund.status != Refund.Status.PENDING:
        return refund
    refund.status = Refund.Status.PROCESSED if processed else Refund.Status.FAILED
    refund.processed_at = timezone.now() if processed else None
    refund.error = error[:300]
    refund.save()
    if not processed:
        _notify_ops(refund, f"Refund failed at the payment provider: {error}")
    return refund


def _notify_ops(refund, message):
    from apps.accounts.models import User

    for ops in User.objects.filter(role=User.Role.OPS, is_active=True):
        notify(
            ops,
            f"Refund {refund.credit_note_number} needs attention",
            message,
            url=reverse("admin:payments_refund_change", args=[refund.pk]),
            email=False,
        )
