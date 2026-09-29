from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Event(models.Model):
    """Append-only audit log. Every important state change writes one row.

    The same log drives campaign timelines on dashboards and evidence packs in disputes.
    """

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    verb = models.CharField(max_length=64, db_index=True)
    message = models.CharField(max_length=500)
    data = models.JSONField(default=dict, blank=True)
    target_type = models.ForeignKey(ContentType, null=True, on_delete=models.SET_NULL)
    target_id = models.CharField(max_length=64, blank=True)
    target = GenericForeignKey("target_type", "target_id")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["target_type", "target_id"])]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.verb}"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=500, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class SentReminder(models.Model):
    """One row per reminder sent, so each reminder goes out once however often jobs run."""

    key = models.CharField(max_length=120, unique=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.key


class JobHeartbeat(models.Model):
    """Last run of a scheduled job, shown on the ops page so a stopped scheduler is noticed."""

    name = models.CharField(max_length=60, unique=True)
    last_run_at = models.DateTimeField()
    last_result = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class DataRequest(models.Model):
    """A person's request to erase their data (DPDP Act). Ops handles it within 30 days."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        DONE = "done", "Completed"
        REJECTED = "rejected", "Declined (explained to the person)"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="data_requests")
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    ops_note = models.TextField(blank=True, help_text="What was deleted, and what is kept and why")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Erasure request by {self.user} ({self.get_status_display()})"
