from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedTextField
from apps.core.models import TimeStampedModel
from apps.niches.models import SensitiveCategory


class Deliverable(models.TextChoices):
    REEL = "reel", "Instagram Reel"
    STORY = "story", "Instagram Story"
    POST = "post", "Feed post / carousel"


class CreatorProfile(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Onboarding"
        PENDING_REVIEW = "pending_review", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class KycStatus(models.TextChoices):
        NOT_SUBMITTED = "not_submitted", "Not submitted"
        PENDING = "pending", "Pending review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    class Gender(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        OTHER = "other", "Other / prefer not to say"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="creator_profile"
    )
    display_name = models.CharField(max_length=120)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    city = models.CharField(max_length=80, blank=True)
    languages = models.JSONField(default=list, blank=True)
    bio = models.TextField(blank=True)
    primary_niche = models.ForeignKey(
        "niches.Niche", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    niches = models.ManyToManyField("niches.Niche", blank=True, related_name="creators")

    # Instagram (filled by the Instagram adapter)
    ig_username = models.CharField(max_length=60, blank=True)
    ig_user_id = models.CharField(max_length=64, blank=True)
    ig_access_token = EncryptedTextField(blank=True)
    ig_token_expires_at = models.DateTimeField(null=True, blank=True)
    ig_connected_at = models.DateTimeField(null=True, blank=True)
    ig_synced_at = models.DateTimeField(null=True, blank=True)
    # Daily sync health. After repeated failures (or an expired token) the creator must
    # reconnect, and isn't matched to new campaigns until they do.
    ig_sync_failures = models.PositiveSmallIntegerField(default=0)
    ig_sync_error = models.CharField(max_length=300, blank=True)
    ig_needs_reconnect = models.BooleanField(default=False)
    followers = models.PositiveIntegerField(default=0)
    avg_reach = models.PositiveIntegerField(default=0, help_text="Average reach per recent post")
    avg_views = models.PositiveIntegerField(default=0, help_text="Average Reel plays")
    engagement_rate = models.FloatField(default=0, help_text="Engagements ÷ reach × 100")
    audience_female_pct = models.FloatField(default=50)
    audience_india_pct = models.FloatField(default=0)
    audience_top_cities = models.JSONField(default=list, blank=True)
    audience_age = models.JSONField(default=dict, blank=True, help_text='e.g. {"18-24": 40}')
    content_keywords = models.JSONField(default=list, blank=True)
    sponsored_posts_30d = models.PositiveSmallIntegerField(default=0)

    # Platform scores
    authenticity_score = models.PositiveSmallIntegerField(default=0)
    reliability_score = models.FloatField(default=0.7, help_text="0-1, from delivery history")

    # Rate card: what the creator receives, in paise (never shown to brands)
    rate_reel = models.PositiveIntegerField(default=0)
    rate_story = models.PositiveIntegerField(default=0)
    rate_post = models.PositiveIntegerField(default=0)

    red_lines = models.JSONField(
        default=list, blank=True, help_text="SensitiveCategory values the creator refuses"
    )
    allows_ai_likeness = models.BooleanField(default=False)
    max_active_campaigns = models.PositiveSmallIntegerField(default=3)
    on_break = models.BooleanField(default=False)

    # KYC and payout details
    legal_name = models.CharField(max_length=200, blank=True)
    pan = EncryptedTextField(blank=True)
    pan_last4 = models.CharField(max_length=4, blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    bank_account_name = models.CharField(max_length=200, blank=True)
    bank_account_number = EncryptedTextField(blank=True)
    bank_account_last4 = models.CharField(max_length=4, blank=True)
    bank_ifsc = models.CharField(max_length=11, blank=True)
    kyc_document = models.FileField(upload_to="kyc/%Y/%m/", blank=True)
    kyc_status = models.CharField(max_length=20, choices=KycStatus.choices, default=KycStatus.NOT_SUBMITTED)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    review_note = models.TextField(blank=True)

    def __str__(self):
        return f"{self.display_name} (@{self.ig_username})" if self.ig_username else self.display_name

    @property
    def tier(self):
        if self.followers < 10_000:
            return "nano"
        if self.followers <= 100_000:
            return "micro"
        return "mid"

    @property
    def ig_connected(self):
        return self.ig_connected_at is not None

    def rate_for(self, deliverable):
        return {
            Deliverable.REEL: self.rate_reel,
            Deliverable.STORY: self.rate_story,
            Deliverable.POST: self.rate_post,
        }[deliverable]

    def red_line_labels(self):
        return [SensitiveCategory(c).label for c in self.red_lines if c in SensitiveCategory.values]
