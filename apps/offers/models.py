from django.db import models

from apps.core.models import TimeStampedModel


class Slot(TimeStampedModel):
    """One creator deliverable in a campaign. A slot keeps its place when a creator declines:
    the next backup is offered the same slot."""

    class Status(models.TextChoices):
        OFFERING = "offering", "Offer sent"
        ACCEPTED = "accepted", "Accepted, awaiting payment"
        CONFIRMED = "confirmed", "Paid, in production"
        UNFILLED = "unfilled", "No creator available"
        CANCELLED = "cancelled", "Cancelled"

    ACTIVE = (Status.OFFERING, Status.ACCEPTED, Status.CONFIRMED)

    campaign = models.ForeignKey("campaigns.Campaign", on_delete=models.CASCADE, related_name="slots")
    position = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OFFERING)
    creator = models.ForeignKey(
        "creators.CreatorProfile", null=True, blank=True, on_delete=models.PROTECT, related_name="slots"
    )
    # Frozen when the creator accepts.
    creator_fee = models.PositiveIntegerField(default=0)
    brand_price = models.PositiveIntegerField(default=0)
    accepted_at = models.DateTimeField(null=True, blank=True)
    payment_due_at = models.DateTimeField(null=True, blank=True)
    order = models.ForeignKey(
        "payments.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="slots"
    )

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["campaign", "position"], name="unique_slot_position")]

    def __str__(self):
        return f"{self.campaign} slot {self.position}"

    @property
    def current_offer(self):
        return self.offers.order_by("-created_at").first()


class Offer(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for creator"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"
        WITHDRAWN = "withdrawn", "Withdrawn"
        RELEASED = "released", "Released (brand didn't pay in time)"

    class DeclineReason(models.TextChoices):
        FEE = "fee", "Fee too low"
        TIMING = "timing", "Timeline doesn't work"
        PRODUCT = "product", "Not a fit for my audience"
        BRAND = "brand", "Don't want to work with this brand"
        BUSY = "busy", "Too busy right now"
        OTHER = "other", "Other"

    slot = models.ForeignKey(Slot, on_delete=models.CASCADE, related_name="offers")
    creator = models.ForeignKey("creators.CreatorProfile", on_delete=models.PROTECT, related_name="offers")
    candidate = models.ForeignKey("matching.MatchCandidate", null=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    # Creator-facing and brand-facing prices, frozen when the offer is made.
    creator_fee = models.PositiveIntegerField()
    brand_price = models.PositiveIntegerField()
    expires_at = models.DateTimeField()
    responded_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.CharField(max_length=10, choices=DeclineReason.choices, blank=True)
    decline_note = models.CharField(max_length=300, blank=True)
    agreement = models.ForeignKey("contracts.Agreement", null=True, blank=True, on_delete=models.PROTECT)
    viewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "expires_at"])]

    def __str__(self):
        return f"Offer to {self.creator} for {self.slot}"

    @property
    def campaign(self):
        return self.slot.campaign
