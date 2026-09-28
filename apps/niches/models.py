from django.db import models


class SensitiveCategory(models.TextChoices):
    """Categories that are blocked or need manual review; creators can also refuse them."""

    ALCOHOL = "alcohol", "Alcohol"
    TOBACCO = "tobacco", "Tobacco / vaping"
    GAMBLING = "gambling", "Gambling / betting / real-money gaming"
    CRYPTO = "crypto", "Crypto / trading apps"
    FINANCIAL = "financial", "Loans / credit / investment products"
    PHARMA = "pharma", "Medicines / health claims"
    SUPPLEMENTS = "supplements", "Supplements / weight loss"
    ADULT = "adult", "Adult / intimate products"
    POLITICAL = "political", "Political / religious"
    WEAPONS = "weapons", "Weapons"
    FAST_FASHION = "fast_fashion", "Fast fashion"


# Categories the platform refuses outright in v1. The rest go to manual review.
BLOCKED_CATEGORIES = {
    SensitiveCategory.TOBACCO,
    SensitiveCategory.GAMBLING,
    SensitiveCategory.ADULT,
    SensitiveCategory.POLITICAL,
    SensitiveCategory.WEAPONS,
}


class Niche(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    keywords = models.JSONField(default=list, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.parent.name} › {self.name}" if self.parent_id else self.name

    @property
    def root(self):
        return self.parent or self
