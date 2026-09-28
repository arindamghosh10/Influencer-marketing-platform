from django.db import models


class MatchRun(models.Model):
    campaign = models.ForeignKey("campaigns.Campaign", on_delete=models.CASCADE, related_name="match_runs")
    brief = models.ForeignKey("campaigns.ProductBrief", on_delete=models.PROTECT)
    eligible_count = models.PositiveIntegerField(default=0)
    excluded_counts = models.JSONField(default=dict, help_text="Exclusion reason -> count")
    shortage = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Match run for {self.campaign} at {self.created_at:%Y-%m-%d %H:%M}"


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
