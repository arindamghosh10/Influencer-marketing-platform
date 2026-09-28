from django.db import models


class MatchRun(models.Model):
    class Purpose(models.TextChoices):
        INITIAL = "initial", "First selection"
        TOP_UP = "top_up", "More creators for a running campaign"

    campaign = models.ForeignKey("campaigns.Campaign", on_delete=models.CASCADE, related_name="match_runs")
    brief = models.ForeignKey("campaigns.ProductBrief", on_delete=models.PROTECT)
    eligible_count = models.PositiveIntegerField(default=0)
    excluded_counts = models.JSONField(default=dict, help_text="Exclusion reason -> count")
    shortage = models.BooleanField(default=False)
    purpose = models.CharField(max_length=10, choices=Purpose.choices, default=Purpose.INITIAL)
    # Top-ups only: extra budget (paise, excl. GST) and creators asked for; sent_at is set
    # once offers go out, after which the run is only used for backups.
    budget = models.PositiveBigIntegerField(null=True, blank=True)
    creators_wanted = models.PositiveSmallIntegerField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Match run for {self.campaign} at {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def is_pending_top_up(self):
        return self.purpose == self.Purpose.TOP_UP and self.sent_at is None

    @property
    def selection_budget(self):
        return self.budget if self.purpose == self.Purpose.TOP_UP else self.campaign.budget


class MatchCandidate(models.Model):
    class Role(models.TextChoices):
        RECOMMENDED = "recommended", "Recommended"
        BACKUP = "backup", "Backup"

    run = models.ForeignKey(MatchRun, on_delete=models.CASCADE, related_name="candidates")
    creator = models.ForeignKey("creators.CreatorProfile", on_delete=models.CASCADE)
    rank = models.PositiveSmallIntegerField()
    role = models.CharField(max_length=12, choices=Role.choices)
    score = models.FloatField()
    components = models.JSONField(default=dict)
    reasons = models.JSONField(default=list)
    # Both prices are frozen at match time. Brand-facing code must only read brand_price;
    # creator-facing code must only read creator_fee (see apps.matching.views_models).
    creator_fee = models.PositiveIntegerField()
    brand_price = models.PositiveIntegerField()
    selected = models.BooleanField(default=False)

    class Meta:
        ordering = ["rank"]
        constraints = [models.UniqueConstraint(fields=["run", "creator"], name="unique_candidate_per_run")]

    def __str__(self):
        return f"#{self.rank} {self.creator} ({self.role})"
