from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel
from apps.creators.models import Deliverable


class Campaign(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        BRIEF_READY = "brief_ready", "Brief ready to review"
        BRIEF_CONFIRMED = "brief_confirmed", "Brief confirmed"
        SHORTLISTED = "shortlisted", "Creators selected"
        OFFERS_OUT = "offers_out", "Offers sent"
        ACTIVE = "active", "In production"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class Objective(models.TextChoices):
        AWARENESS = "awareness", "Awareness (reach)"
        ENGAGEMENT = "engagement", "Engagement"
        TRAFFIC = "traffic", "Website traffic"
        SALES = "sales", "Sales"
        CONTENT = "content", "Content only (assets for my own channels)"

    class Gender(models.TextChoices):
        ANY = "any", "Any"
        FEMALE = "female", "Mostly women"
        MALE = "male", "Mostly men"

    class ContentMode(models.TextChoices):
        CREATOR_MADE = "creator_made", "Creator films it (AI helps with script)"
        AI_LIKENESS = "ai_likeness", "AI-assisted with creator's likeness (creator approves)"

    brand = models.ForeignKey("brands.BrandProfile", on_delete=models.CASCADE, related_name="campaigns")
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    objective = models.CharField(max_length=20, choices=Objective.choices, default=Objective.AWARENESS)
    product_url = models.URLField(blank=True, max_length=1000)
    product_notes = models.TextField(blank=True, help_text="Anything else about the product")
    product_image = models.ImageField(upload_to="products/%Y/%m/", blank=True)
    budget = models.PositiveBigIntegerField(help_text="Paise, excluding GST")
    creators_wanted = models.PositiveSmallIntegerField(null=True, blank=True)
    deliverable = models.CharField(max_length=10, choices=Deliverable.choices, default=Deliverable.REEL)
    target_gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.ANY)
    target_cities = models.JSONField(default=list, blank=True)
    languages = models.JSONField(default=list, blank=True)
    content_mode = models.CharField(
        max_length=20, choices=ContentMode.choices, default=ContentMode.CREATOR_MADE
    )
    usage_rights_days = models.PositiveSmallIntegerField(default=90)
    paid_ads_allowed = models.BooleanField(default=True)
    must_say = models.TextField(blank=True)
    must_not_say = models.TextField(blank=True)
    content_deadline = models.DateField(null=True, blank=True)
    # Copied from settings at creation so later changes don't reprice live campaigns.
    margin_bps = models.PositiveIntegerField()
    # Campaigns in sensitive categories need an ops sign-off before offers go out.
    ops_approved_at = models.DateTimeField(null=True, blank=True)
    ops_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.margin_bps is None:
            self.margin_bps = settings.PLATFORM_MARGIN_BPS
        super().save(*args, **kwargs)

    @property
    def current_brief(self):
        return self.briefs.order_by("-version").first()

    @property
    def confirmed_brief(self):
        return self.briefs.filter(confirmed_at__isnull=False).order_by("-version").first()


class ProductBrief(models.Model):
    class Source(models.TextChoices):
        GEMINI = "gemini", "AI (Gemini)"
        RULES = "rules", "Automatic (rule-based)"
        EDITED = "edited", "Edited by brand"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="briefs")
    version = models.PositiveSmallIntegerField()
    source = models.CharField(max_length=10, choices=Source.choices)
    data = models.JSONField(help_text="BriefData (see apps.integrations.llm.schema)")
    fetch_error = models.CharField(max_length=300, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        constraints = [models.UniqueConstraint(fields=["campaign", "version"], name="unique_brief_version")]

    def __str__(self):
        return f"{self.campaign} brief v{self.version}"
