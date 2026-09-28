from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Asset(models.Model):
    """One uploaded draft version for a slot. Files are never replaced: a new upload is a new
    version, and approvals point at the exact file by its SHA-256."""

    class Status(models.TextChoices):
        IN_REVIEW = "in_review", "With brand for review"
        CHANGES_REQUESTED = "changes_requested", "Changes requested"
        APPROVED = "approved", "Approved by brand"
        FINAL = "final", "Final (creator approved)"
        SUPERSEDED = "superseded", "Replaced by a newer version"

    slot = models.ForeignKey("offers.Slot", on_delete=models.CASCADE, related_name="assets")
    version = models.PositiveSmallIntegerField()
    file = models.FileField(upload_to="content/%Y/%m/")
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    caption = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_REVIEW)
    checks = models.JSONField(default=list, help_text="Automated check results")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        constraints = [models.UniqueConstraint(fields=["slot", "version"], name="unique_asset_version")]

    def __str__(self):
        return f"{self.slot} v{self.version}"

    @property
    def is_video(self):
        return self.content_type.startswith("video/")


class Review(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        CHANGES = "changes", "Changes requested"
        AUTO_APPROVED = "auto_approved", "Auto-approved (no response in time)"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    decision = models.CharField(max_length=16, choices=Decision.choices)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.asset}: {self.decision}"


class Post(TimeStampedModel):
    """The published Instagram post for a slot, and its verification state."""

    class Method(models.TextChoices):
        API = "api", "Published automatically"
        SELF = "self", "Posted by the creator"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        AWAITING_SELF_POST = "awaiting_self_post", "Waiting for creator to post"
        LIVE = "live", "Live"
        MISSING = "missing", "Missing or edited"
        VERIFIED = "verified", "Verified"
        FAILED = "failed", "Publishing failed"

    slot = models.OneToOneField("offers.Slot", on_delete=models.CASCADE, related_name="post")
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    method = models.CharField(max_length=10, choices=Method.choices)
    status = models.CharField(max_length=20, choices=Status.choices)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    publish_attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    ig_media_id = models.CharField(max_length=64, blank=True)
    permalink = models.URLField(blank=True, max_length=500)
    published_at = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    missing_since = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    monitoring_ends_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Post for {self.slot}"


class MetricSnapshot(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="snapshots")
    captured_at = models.DateTimeField(auto_now_add=True)
    reach = models.PositiveIntegerField(default=0)
    views = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    comments = models.PositiveIntegerField(default=0)
    shares = models.PositiveIntegerField(default=0)
    saves = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-captured_at"]

    def __str__(self):
        return f"{self.post} @ {self.captured_at:%Y-%m-%d %H:%M}"

    @property
    def engagements(self):
        return self.likes + self.comments + self.shares + self.saves
