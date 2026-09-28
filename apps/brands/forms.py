from django import forms

from apps.core.forms import StyledFormMixin, UpperCharField, split_csv
from apps.core.validators import validate_gstin, validate_pan
from apps.niches.models import Niche

from .models import BrandProfile


class BrandProfileForm(StyledFormMixin, forms.ModelForm):
    website = forms.URLField(required=False, assume_scheme="https")
    competitors_csv = forms.CharField(
        label="Main competitors",
        required=False,
        help_text="Comma separated. Creators who recently promoted them are flagged.",
    )
    niches = forms.ModelMultipleChoiceField(
        queryset=Niche.objects.filter(parent__isnull=True),
        widget=forms.CheckboxSelectMultiple,
        label="Categories you sell in",
    )

    class Meta:
        model = BrandProfile
        fields = ["company_name", "website", "description", "niches", "gstin", "pan", "billing_address"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "billing_address": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {"gstin": "GSTIN", "pan": "Company PAN"}
        help_texts = {"gstin": "Needed for GST invoices (input tax credit)."}

    gstin = UpperCharField(
        label="GSTIN",
        max_length=15,
        validators=[validate_gstin],
        help_text="Needed for GST invoices (input tax credit).",
    )
    pan = UpperCharField(label="Company PAN", max_length=10, required=False, validators=[validate_pan])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["competitors_csv"].initial = ", ".join(self.instance.competitors or [])

    def clean(self):
        cleaned = super().clean()
        gstin, pan = cleaned.get("gstin"), cleaned.get("pan")
        if gstin and pan and gstin[2:12] != pan:
            self.add_error("pan", "PAN doesn't match the PAN inside your GSTIN.")
        if gstin and not pan:
            cleaned["pan"] = gstin[2:12]
        return cleaned

    def save(self, commit=True):
        self.instance.competitors = split_csv(self.cleaned_data["competitors_csv"])
        if not self.instance.pan and self.cleaned_data.get("gstin"):
            self.instance.pan = self.cleaned_data["gstin"][2:12]
        return super().save(commit)
