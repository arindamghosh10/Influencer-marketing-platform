import secrets

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel
from apps.core.validators import validate_gstin, validate_pan


class BrandProfile(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Onboarding"
        PENDING_REVIEW = "pending_review", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="brand_profile"
    )
    company_name = models.CharField(max_length=200)
    website = models.URLField(blank=True)
    description = models.TextField(blank=True, help_text="What the brand sells and to whom.")
    niches = models.ManyToManyField("niches.Niche", blank=True, related_name="brands")
    gstin = models.CharField(max_length=15, blank=True, validators=[validate_gstin])
    pan = models.CharField(max_length=10, blank=True, validators=[validate_pan])
    billing_address = models.TextField(blank=True)
    competitors = models.JSONField(default=list, blank=True)
    domain_verification_token = models.CharField(max_length=64, blank=True)
    domain_verified_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    review_note = models.TextField(blank=True)

    def __str__(self):
        return self.company_name

    @property
    def domain(self):
        from urllib.parse import urlparse

        host = urlparse(self.website).hostname or ""
        return host.removeprefix("www.")

    def ensure_verification_token(self):
        if not self.domain_verification_token:
            self.domain_verification_token = secrets.token_hex(16)
            self.save(update_fields=["domain_verification_token"])
        return self.domain_verification_token

    @property
    def dns_txt_record(self):
        return f"creatorbridge-verification={self.domain_verification_token}"
