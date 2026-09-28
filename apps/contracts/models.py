from django.conf import settings
from django.db import models


class AgreementKind(models.TextChoices):
    CREATOR_PLATFORM = "creator_platform", "Creator platform agreement"
    BRAND_PLATFORM = "brand_platform", "Brand platform agreement"
    CREATOR_CAMPAIGN = "creator_campaign", "Creator campaign agreement"
    BRAND_ORDER = "brand_order", "Brand campaign order"


class Agreement(models.Model):
    """A signed contract. The exact rendered text and its SHA-256 hash are stored, so what
    the user saw can always be proven later. Rows are never edited after signing."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="agreements")
    kind = models.CharField(max_length=32, choices=AgreementKind.choices)
    version = models.CharField(max_length=16)
    campaign = models.ForeignKey("campaigns.Campaign", null=True, blank=True, on_delete=models.PROTECT)
    body = models.TextField()
    sha256 = models.CharField(max_length=64)
    signed_name = models.CharField(max_length=200)
    signed_at = models.DateTimeField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    otp_verified = models.BooleanField(default=False)

    class Meta:
        ordering = ["-signed_at"]

    def __str__(self):
        return f"{self.get_kind_display()} v{self.version} — {self.user}"


class ConsentScope(models.TextChoices):
    TERMS = "terms", "Platform terms"
    DATA_PROCESSING = "data_processing", "Personal data processing (DPDP)"
    INSTAGRAM_READ = "instagram_read", "Read Instagram profile, media and insights"
    INSTAGRAM_PUBLISH = "instagram_publish", "Publish approved content on my Instagram"
    AI_SCRIPT_HELP = "ai_script_help", "AI help with scripts and captions"
    AI_LIKENESS = "ai_likeness", "AI-generated content using my likeness (per campaign)"
    PAID_ADS_USAGE = "paid_ads_usage", "Brand may use campaign content in paid ads"
    MARKETING = "marketing", "Marketing messages"


class ConsentEvent(models.Model):
    class Action(models.TextChoices):
        GRANTED = "granted", "Granted"
        REVOKED = "revoked", "Revoked"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="consent_events"
    )
    scope = models.CharField(max_length=32, choices=ConsentScope.choices)
    action = models.CharField(max_length=10, choices=Action.choices)
    agreement = models.ForeignKey(Agreement, null=True, blank=True, on_delete=models.PROTECT)
    campaign = models.ForeignKey("campaigns.Campaign", null=True, blank=True, on_delete=models.PROTECT)
    asset_sha256 = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} {self.action} {self.scope}"


class OneTimeCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=64)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.purpose} code for {self.user}"
