from django import forms
from django.utils import timezone

from apps.core.forms import StyledFormMixin, split_csv
from apps.core.money import rupees_to_paise
from apps.niches.models import Niche

from .models import Campaign

MIN_BUDGET_RUPEES = 5_000


class CampaignForm(StyledFormMixin, forms.ModelForm):
    product_url = forms.URLField(
        label="Product page link", required=False, max_length=1000, assume_scheme="https"
    )
    budget_rupees = forms.IntegerField(
        label="Budget (₹, excluding GST)",
        min_value=MIN_BUDGET_RUPEES,
        help_text=f"Minimum ₹{MIN_BUDGET_RUPEES:,}. You only pay for creators who accept.",
    )
    target_cities_csv = forms.CharField(
        label="Target cities", required=False, help_text="Comma separated. Leave empty for all of India."
    )
    languages_csv = forms.CharField(
        label="Content languages", required=False, help_text="e.g. Hindi, English. Leave empty for any."
    )

    class Meta:
        model = Campaign
        fields = [
            "title",
            "product_url",
            "product_notes",
            "product_image",
            "objective",
            "deliverable",
            "creators_wanted",
            "target_gender",
            "content_mode",
            "usage_rights_days",
            "paid_ads_allowed",
            "must_say",
            "must_not_say",
            "content_deadline",
        ]
        widgets = {
            "product_notes": forms.Textarea(attrs={"rows": 3}),
            "must_say": forms.Textarea(attrs={"rows": 2}),
            "must_not_say": forms.Textarea(attrs={"rows": 2}),
            "content_deadline": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "title": "Campaign name",
            "product_url": "Product page link",
            "product_notes": "About the product (optional if you give a link)",
            "creators_wanted": "Number of creators (leave empty and we'll suggest)",
            "target_gender": "Audience",
            "usage_rights_days": "Days you can reuse the content (incl. paid ads)",
            "paid_ads_allowed": "I want to use this content in paid ads",
            "must_say": "Must mention",
            "must_not_say": "Must NOT mention",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        if inst.pk:
            self.fields["budget_rupees"].initial = inst.budget // 100
            self.fields["target_cities_csv"].initial = ", ".join(inst.target_cities)
            self.fields["languages_csv"].initial = ", ".join(inst.languages)

    def clean_content_deadline(self):
        deadline = self.cleaned_data.get("content_deadline")
        if deadline and deadline < timezone.localdate() + timezone.timedelta(days=5):
            raise forms.ValidationError("Give creators at least 5 days.")
        return deadline

    def clean(self):
        cleaned = super().clean()
        if not (cleaned.get("product_url") or cleaned.get("product_notes")):
            raise forms.ValidationError("Add a product link or describe the product.")
        return cleaned

    def save(self, commit=True):
        inst = self.instance
        inst.budget = rupees_to_paise(self.cleaned_data["budget_rupees"])
        inst.target_cities = split_csv(self.cleaned_data["target_cities_csv"])
        inst.languages = split_csv(self.cleaned_data["languages_csv"])
        return super().save(commit)


def _lines(value):
    return [line.strip(" -•\t") for line in (value or "").splitlines() if line.strip(" -•\t")]


class BriefEditForm(StyledFormMixin, forms.Form):
    product_name = forms.CharField(max_length=200)
    brand_name = forms.CharField(max_length=200, required=False)
    category = forms.CharField(max_length=100, required=False)
    summary = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)
    key_features = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}), required=False, help_text="One per line"
    )
    benefits = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}), required=False, help_text="One per line"
    )
    target_audience = forms.CharField(max_length=300, required=False)
    niches = forms.ModelMultipleChoiceField(
        queryset=Niche.objects.filter(parent__isnull=False).select_related("parent"),
        help_text="Up to 3. Hold Ctrl/Cmd to pick several.",
    )
    keywords = forms.CharField(required=False, help_text="Comma separated topics")

    def clean_niches(self):
        niches = self.cleaned_data["niches"]
        if len(niches) > 3:
            raise forms.ValidationError("Pick at most 3.")
        return niches

    @classmethod
    def from_brief(cls, data, post=None):
        initial = {
            **{
                k: data.get(k, "")
                for k in ("product_name", "brand_name", "category", "summary", "target_audience")
            },
            "key_features": "\n".join(data.get("key_features", [])),
            "benefits": "\n".join(data.get("benefits", [])),
            "niches": Niche.objects.filter(slug__in=data.get("niche_slugs", [])),
            "keywords": ", ".join(data.get("keywords", [])),
        }
        return cls(post, initial=initial)

    def merged(self, data):
        c = self.cleaned_data
        return {
            **data,
            "product_name": c["product_name"],
            "brand_name": c["brand_name"],
            "category": c["category"],
            "summary": c["summary"],
            "key_features": _lines(c["key_features"]),
            "benefits": _lines(c["benefits"]),
            "target_audience": c["target_audience"],
            "niche_slugs": [n.slug for n in c["niches"]],
            "keywords": [k.lower() for k in split_csv(c["keywords"])],
        }
