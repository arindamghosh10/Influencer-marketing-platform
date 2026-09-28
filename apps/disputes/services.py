"""Disputes between a brand and a creator about one campaign slot.

While a dispute is open the creator's payout can't be released. Ops reviews the evidence pack
(everything recorded about the slot) and resolves it: pay the creator, refund the brand, split,
or no change.
"""

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.core.events import events_for, notify, record
from apps.offers.models import Offer, Slot

from .models import Dispute

DISPUTABLE_STATES = (*Slot.IN_PROGRESS, Slot.Status.VERIFIED)


class DisputeError(Exception):
    pass


def has_open_dispute(slot):
    return Dispute.objects.filter(slot=slot, status=Dispute.Status.OPEN).exists()


def open_dispute(slot):
    return Dispute.objects.filter(slot=slot, status=Dispute.Status.OPEN).first()


def can_raise(slot):
    from apps.payments.models import Payout

    if slot.status not in DISPUTABLE_STATES:
        return False
    payout = Payout.objects.filter(slot=slot).first()
    return not (payout and payout.status == Payout.Status.PAID)


def raise_dispute(slot, user, party, category, description):
    if not can_raise(slot):
        raise DisputeError(
            "A problem can only be reported while the campaign is in progress and before payout."
        )
    allowed = Dispute.BRAND_CATEGORIES if party == Dispute.Party.BRAND else Dispute.CREATOR_CATEGORIES
    if category not in allowed:
        raise DisputeError("Choose one of the listed problems.")
    try:
        with transaction.atomic():
            dispute = Dispute.objects.create(
                slot=slot, raised_by=user, party=party, category=category, description=description[:3000]
            )
    except IntegrityError as exc:
        raise DisputeError("There's already an open report for this creator. Our team is on it.") from exc
    campaign = slot.campaign
    record(
        "dispute.opened",
        f"{dispute.get_party_display()} reported: {dispute.get_category_display()}",
        actor=user,
        target=campaign,
        data={"dispute": dispute.pk},
    )
    other = slot.creator.user if party == Dispute.Party.BRAND else campaign.brand.user
    other_url = (
        reverse("content:workspace", args=[slot.pk])
        if party == Dispute.Party.BRAND
        else reverse("content:review", args=[campaign.pk, slot.pk])
    )
    notify(
        other,
        f"A problem was reported on '{campaign.title}'",
        f"{dispute.get_category_display()}. Our team will review everything and get back to both of you. "
        "Payment is on hold until then.",
        url=other_url,
    )
    from apps.accounts.models import User

    for ops in User.objects.filter(role=User.Role.OPS, is_active=True):
        notify(
            ops,
            f"New dispute #{dispute.pk}: {dispute.get_category_display()}",
            description[:300],
            url=reverse("disputes:detail", args=[dispute.pk]),
            email=False,
        )
    return dispute


def evidence(dispute):
    """Everything recorded about the disputed slot, for ops to decide."""
    from apps.content.models import Asset, Post
    from apps.contracts.models import ConsentEvent
    from apps.payments.models import Payout, Refund

    slot = dispute.slot
    campaign = slot.campaign
    accepted = slot.offers.filter(status=Offer.Status.ACCEPTED).select_related("agreement").first()
    agreements = [
        a
        for a in [accepted.agreement if accepted else None, slot.order.agreement if slot.order else None]
        if a
    ]
    post = Post.objects.filter(slot=slot).first()
    return {
        "slot": slot,
        "campaign": campaign,
        "brief": campaign.confirmed_brief.data if campaign.confirmed_brief else {},
        "offer": accepted,
        "agreements": agreements,
        "consents": ConsentEvent.objects.filter(
            campaign=campaign, user__in=[slot.creator.user, campaign.brand.user]
        ).select_related("user"),
        "assets": Asset.objects.filter(slot=slot).prefetch_related("reviews__reviewer"),
        "post": post,
        "snapshots": post.snapshots.all()[:20] if post else [],
        "payout": Payout.objects.filter(slot=slot).first(),
        "refunds": Refund.objects.filter(slot=slot),
        "events": events_for(campaign)[:100],
        "other_disputes": Dispute.objects.filter(slot=slot).exclude(pk=dispute.pk),
    }


@transaction.atomic
def resolve(dispute, resolution, note, actor, refund_amount=0):
    """refund_amount (paise, taxable) is used for SPLIT."""
    from apps.payments.models import Payout
    from apps.payments.refunds import issue_refund
    from apps.payments.tax import payout_breakdown

    dispute = Dispute.objects.select_for_update().get(pk=dispute.pk)
    if dispute.status != Dispute.Status.OPEN:
        raise DisputeError("This dispute is already resolved.")
    slot = (
        Slot.objects.select_for_update(of=("self",))
        .select_related("campaign__brand__user", "creator__user", "order")
        .get(pk=dispute.slot_id)
    )
    payout = Payout.objects.select_for_update().filter(slot=slot).first()
    if payout and payout.status == Payout.Status.PAID and resolution != Dispute.Resolution.NO_CHANGE:
        raise DisputeError("The creator has already been paid; recover funds manually before refunding.")
    refund = None

    if resolution == Dispute.Resolution.REFUND_FULL:
        refund = issue_refund(
            slot.order,
            slot.brand_price,
            f"Dispute #{dispute.pk} resolved in your favour",
            slot=slot,
            actor=actor,
        )
        if payout:
            payout.status = Payout.Status.CANCELLED
            payout.save(update_fields=["status", "updated_at"])
        slot.status = Slot.Status.CANCELLED
        slot.save(update_fields=["status", "updated_at"])
        post = getattr(slot, "post", None)
        if post:
            post.next_check_at = None
            post.save(update_fields=["next_check_at", "updated_at"])
    elif resolution == Dispute.Resolution.SPLIT:
        if not 0 < refund_amount < slot.brand_price:
            raise DisputeError(
                "For a split, refund part of the price (more than zero, less than the full price)."
            )
        refund = issue_refund(
            slot.order, refund_amount, f"Dispute #{dispute.pk}: partial refund", slot=slot, actor=actor
        )
        if payout:
            kept = 1 - refund_amount / slot.brand_price
            b = payout_breakdown(slot.creator, round(slot.creator_fee * kept))
            payout.gross, payout.gst, payout.tds, payout.tds_rate_bps, payout.net = (
                b.gross,
                b.gst,
                b.tds,
                b.tds_rate_bps,
                b.net,
            )
            payout.save()

    release = resolution != Dispute.Resolution.REFUND_FULL and payout and payout.status == Payout.Status.HELD
    if release and slot.status == Slot.Status.VERIFIED:
        payout.status = Payout.Status.RELEASABLE
        payout.save(update_fields=["status", "updated_at"])

    dispute.status = Dispute.Status.RESOLVED
    dispute.resolution = resolution
    dispute.resolution_note = note
    dispute.refund = refund
    dispute.resolved_by = actor
    dispute.resolved_at = timezone.now()
    dispute.save()
    record(
        "dispute.resolved",
        f"Dispute #{dispute.pk} resolved: {dispute.get_resolution_display()}",
        actor=actor,
        target=slot.campaign,
        data={"note": note},
    )
    message = f"{dispute.get_resolution_display()}. {note}".strip()
    notify(
        slot.creator.user,
        "Dispute resolved",
        message,
        url=reverse("content:workspace", args=[slot.pk])
        if slot.status != Slot.Status.CANCELLED
        else reverse("creators:dashboard"),
    )
    notify(
        slot.campaign.brand.user,
        "Dispute resolved",
        message,
        url=reverse("campaigns:detail", args=[slot.campaign_id]),
    )
    from apps.content.services import maybe_complete_campaign

    maybe_complete_campaign(slot.campaign)
    return dispute
