from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Dispute(TimeStampedModel):
    class Party(models.TextChoices):
        BRAND = "brand", "Brand"
        CREATOR = "creator", "Creator"

    class Category(models.TextChoices):
        OFF_BRIEF = "off_brief", "Content doesn't follow the brief"
        UNRESPONSIVE_CREATOR = "unresponsive_creator", "Creator unresponsive or missed the deadline"
        POST_CHANGED = "post_changed", "Post removed or changed"
        UNRESPONSIVE_BRAND = "unresponsive_brand", "Brand unresponsive"
        SCOPE = "scope", "Asked for changes outside the brief"
        PAYMENT = "payment", "Payment problem"
        OTHER = "other", "Something else"

    BRAND_CATEGORIES = [
        Category.OFF_BRIEF,
        Category.UNRESPONSIVE_CREATOR,
        Category.POST_CHANGED,
        Category.OTHER,
    ]
    CREATOR_CATEGORIES = [Category.UNRESPONSIVE_BRAND, Category.SCOPE, Category.PAYMENT, Category.OTHER]

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    class Resolution(models.TextChoices):
        PAY_CREATOR = "pay_creator", "Creator is paid in full"
        REFUND_FULL = "refund_full", "Brand refunded in full, creator not paid"
        SPLIT = "split", "Partial refund to brand, creator paid the rest"
        NO_CHANGE = "no_change", "No change: campaign continues as normal"

    slot = models.ForeignKey("offers.Slot", on_delete=models.PROTECT, related_name="disputes")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    party = models.CharField(max_length=10, choices=Party.choices)
    category = models.CharField(max_length=24, choices=Category.choices)
    description = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    resolution = models.CharField(max_length=12, choices=Resolution.choices, blank=True)
    resolution_note = models.TextField(blank=True, help_text="Shown to both sides")
    refund = models.ForeignKey("payments.Refund", null=True, blank=True, on_delete=models.PROTECT)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["slot"], condition=models.Q(status="open"), name="one_open_dispute_per_slot"
            )
        ]

    def __str__(self):
        return f"Dispute #{self.pk} on {self.slot}"
