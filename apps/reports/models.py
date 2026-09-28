from django.db import models


class WeeklyReportLog(models.Model):
    """One row per brand per ISO week, so the weekly digest is never sent twice."""

    brand = models.ForeignKey("brands.BrandProfile", on_delete=models.CASCADE)
    week = models.CharField(max_length=8)  # e.g. "2026-W40"
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["brand", "week"], name="one_report_per_week")]

    def __str__(self):
        return f"{self.brand} {self.week}"
