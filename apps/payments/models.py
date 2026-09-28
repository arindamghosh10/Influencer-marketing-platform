from django.conf import settings
from django.db import models, transaction

from apps.core.models import TimeStampedModel


class Order(TimeStampedModel):
    """What a brand pays for: the accepted creators of one campaign at one time."""

    class Status(models.TextChoices):
        AWAITING_SIGNATURE = "awaiting_signature", "Awaiting order signature"
        CREATED = "created", "Awaiting payment"
        PAID = "paid", "Paid"
        FAILED = "failed", "Payment failed"
        CANCELLED = "cancelled", "Cancelled"

    campaign = models.ForeignKey("campaigns.Campaign", on_delete=models.PROTECT, related_name="orders")
    brand = models.ForeignKey("brands.BrandProfile", on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AWAITING_SIGNATURE)
    subtotal = models.PositiveBigIntegerField()
    cgst = models.PositiveBigIntegerField(default=0)
    sgst = models.PositiveBigIntegerField(default=0)
    igst = models.PositiveBigIntegerField(default=0)
    total = models.PositiveBigIntegerField()
    agreement = models.ForeignKey("contracts.Agreement", null=True, blank=True, on_delete=models.PROTECT)
    provider = models.CharField(max_length=20)
    provider_order_id = models.CharField(max_length=100, blank=True, db_index=True)
    provider_payment_id = models.CharField(max_length=100, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    invoice_number = models.CharField(max_length=30, blank=True, unique=True, null=True)
    # Snapshot of line items so the invoice never changes after payment.
    lines = models.JSONField(default=list)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.pk} ({self.campaign})"

    @property
    def gst_total(self):
        return self.cgst + self.sgst + self.igst


class InvoiceSequence(models.Model):
    """Gap-free invoice numbers per Indian financial year, as GST rules require."""

    financial_year = models.CharField(max_length=7, unique=True)  # e.g. "2026-27"
    last_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.financial_year}: {self.last_number}"

    @classmethod
    def next_number(cls, today):
        start = today.year if today.month >= 4 else today.year - 1
        fy = f"{start}-{str(start + 1)[-2:]}"
        with transaction.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(financial_year=fy)
            seq.last_number += 1
            seq.save(update_fields=["last_number"])
        return f"{settings.INVOICE_PREFIX}/{fy}/{seq.last_number:05d}"


class Payout(TimeStampedModel):
    """Money owed to a creator for one slot. Held until the post is verified live."""

    class Status(models.TextChoices):
        HELD = "held", "Held until post is verified"
        RELEASABLE = "releasable", "Ready to pay"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    slot = models.OneToOneField("offers.Slot", on_delete=models.PROTECT, related_name="payout")
    creator = models.ForeignKey("creators.CreatorProfile", on_delete=models.PROTECT, related_name="payouts")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.HELD)
    gross = models.PositiveIntegerField(help_text="Creator fee")
    gst = models.PositiveIntegerField(default=0, help_text="Added if the creator is GST-registered")
    tds = models.PositiveIntegerField()
    tds_rate_bps = models.PositiveIntegerField()
    net = models.PositiveIntegerField(help_text="gross + gst - tds")
    utr = models.CharField(max_length=40, blank=True, help_text="Bank transfer reference")
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Payout to {self.creator} for {self.slot}"


class WebhookEvent(models.Model):
    """Every payment webhook we accept, stored once (by provider event id) for idempotency."""

    provider = models.CharField(max_length=20)
    event_id = models.CharField(max_length=100)
    event_type = models.CharField(max_length=60)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "event_id"], name="unique_webhook_event")]

    def __str__(self):
        return f"{self.provider} {self.event_type} {self.event_id}"
