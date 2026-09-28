"""Brand orders and creator payouts.

Order flow: accepted, unpaid slots → Order (AWAITING_SIGNATURE) → brand signs the campaign order
→ provider order created (CREATED) → payment verified → PAID. Marking an order paid is idempotent
and can be triggered by the checkout callback or the webhook, whichever arrives first.
"""

import logging

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.campaigns.models import Campaign
from apps.core.events import notify, record
from apps.core.money import format_inr
from apps.integrations.registry import get_provider
from apps.offers.models import Slot

from .models import InvoiceSequence, Order, Payout
from .tax import gst_split, payout_breakdown

log = logging.getLogger(__name__)


class OrderError(Exception):
    pass


def payable_slots(campaign):
    return campaign.slots.filter(status=Slot.Status.ACCEPTED).select_related("creator")


@transaction.atomic
def start_order(campaign):
    """Create an order for all accepted, unpaid slots. Replaces any unfinished order."""
    campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    for stale in campaign.orders.filter(status__in=[Order.Status.AWAITING_SIGNATURE, Order.Status.CREATED]):
        stale.status = Order.Status.CANCELLED
        stale.save(update_fields=["status", "updated_at"])
        Slot.objects.filter(order=stale, status=Slot.Status.ACCEPTED).update(order=None)
    slots = list(payable_slots(campaign))
    if not slots:
        raise OrderError("There's nothing to pay for yet: no creator has accepted.")
    subtotal = sum(s.brand_price for s in slots)
    split = gst_split(subtotal, campaign.brand.gstin)
    order = Order.objects.create(
        campaign=campaign,
        brand=campaign.brand,
        subtotal=subtotal,
        cgst=split.cgst,
        sgst=split.sgst,
        igst=split.igst,
        total=subtotal + split.total,
        provider=get_provider("payments").name,
        lines=[
            {
                "slot": s.pk,
                "creator": s.creator.display_name,
                "handle": s.creator.ig_username,
                "deliverable": campaign.get_deliverable_display(),
                "amount": s.brand_price,
            }
            for s in slots
        ],
    )
    Slot.objects.filter(pk__in=[s.pk for s in slots]).update(order=order)
    return order


@transaction.atomic
def attach_agreement(order, agreement):
    """After the brand signs: create the provider order so checkout can start."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != Order.Status.AWAITING_SIGNATURE:
        return order
    provider = get_provider("payments")
    order.agreement = agreement
    order.provider = provider.name
    order.provider_order_id = provider.create_order(order)
    order.status = Order.Status.CREATED
    order.save(update_fields=["agreement", "provider", "provider_order_id", "status", "updated_at"])
    return order


def mark_paid(order_id, payment_id, amount=None):
    """Idempotent. Returns the order. Safe to call from both callback and webhook."""
    with transaction.atomic():
        order = Order.objects.select_for_update().select_related("campaign__brand__user").get(pk=order_id)
        if order.status == Order.Status.PAID:
            return order
        if amount is not None and amount != order.total:
            raise OrderError(f"Paid amount {amount} doesn't match order total {order.total}")
        now = timezone.now()
        order.status = Order.Status.PAID
        order.provider_payment_id = payment_id
        order.paid_at = now
        order.invoice_number = InvoiceSequence.next_number(timezone.localdate(now))
        order.save()

        campaign = order.campaign
        stale = []
        for slot in (
            Slot.objects.select_for_update(of=("self",)).filter(order=order).select_related("creator__user")
        ):
            if slot.status != Slot.Status.ACCEPTED:
                # Released or cancelled while the brand was paying: needs a refund.
                stale.append(slot)
                continue
            slot.status = Slot.Status.CONFIRMED
            slot.save(update_fields=["status", "updated_at"])
            b = payout_breakdown(slot.creator, slot.creator_fee)
            Payout.objects.create(
                slot=slot,
                creator=slot.creator,
                gross=b.gross,
                gst=b.gst,
                tds=b.tds,
                tds_rate_bps=b.tds_rate_bps,
                net=b.net,
            )
            deadline = campaign.content_deadline
            notify(
                slot.creator.user,
                f"Payment secured: start creating for {campaign.brand.company_name}",
                f"Your fee of {format_inr(slot.creator_fee)} is reserved for you and paid after your post "
                f"has been live for the verification period."
                + (f" Content is due by {deadline:%d %b %Y}." if deadline else ""),
                url=reverse("creators:dashboard"),
            )
        if campaign.status in (Campaign.Status.OFFERS_OUT, Campaign.Status.SHORTLISTED):
            campaign.status = Campaign.Status.ACTIVE
            campaign.save(update_fields=["status", "updated_at"])
        record(
            "order.paid",
            f"Order #{order.pk} paid: {format_inr(order.total)} (invoice {order.invoice_number})",
            target=campaign,
            data={"payment_id": payment_id, "refund_needed_slots": [s.pk for s in stale]},
        )
    notify(
        campaign.brand.user,
        f"Payment received: {format_inr(order.total)}",
        f"Invoice {order.invoice_number} is ready. Your creators have been told to start.",
        url=reverse("payments:invoice", args=[order.pk]),
    )
    if stale:
        _flag_refund(order, stale)
    return order


def _flag_refund(order, slots):
    """Slots released while the brand was paying: refund them automatically."""
    from .refunds import issue_refund

    for slot in slots:
        log.warning("Order %s paid for released slot %s; refunding", order.pk, slot.pk)
        issue_refund(order, slot.brand_price, "Creator was released before your payment completed", slot=slot)


def creator_earnings(creator):
    from django.db.models import Sum

    payouts = Payout.objects.filter(creator=creator)
    month_start = timezone.localdate().replace(day=1)
    return {
        "held": payouts.filter(status=Payout.Status.HELD).aggregate(t=Sum("net"))["t"] or 0,
        "releasable": payouts.filter(status=Payout.Status.RELEASABLE).aggregate(t=Sum("net"))["t"] or 0,
        "paid_month": payouts.filter(status=Payout.Status.PAID, paid_at__date__gte=month_start).aggregate(
            t=Sum("net")
        )["t"]
        or 0,
    }
