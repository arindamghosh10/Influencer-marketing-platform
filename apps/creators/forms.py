from django import forms

from apps.core.forms import StyledFormMixin, UpperCharField, split_csv
from apps.core.money import rupees_to_paise
from apps.core.validators import validate_gstin, validate_ifsc, validate_pan
from apps.niches.models import Niche, SensitiveCategory

from .models import CreatorProfile


class NicheChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return str(obj)


class ProfileForm(StyledFormMixin, forms.ModelForm):
    languages_csv = forms.CharField(
        label="Languages you create in", required=False, help_text="Comma separated, e.g. Hindi, English"
    )
    primary_niche = NicheChoiceField(
        queryset=Niche.objects.filter(parent__isnull=False).select_related("parent"),
        label="Main niche",
        help_text="The one topic most of your content is about.",
    )
    niches = forms.ModelMultipleChoiceField(
        queryset=Niche.objects.filter(parent__isnull=False).select_related("parent"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Other niches (up to 3)",
    )

    class Meta:
        model = CreatorProfile
        fields = ["display_name", "gender", "city", "bio", "primary_niche", "niches"]
        widgets = {"bio": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["languages_csv"].initial = ", ".join(self.instance.languages or [])

    def clean_niches(self):
        niches = self.cleaned_data["niches"]
        if len(niches) > 3:
            raise forms.ValidationError("Pick at most 3 other niches.")
        return niches

    def save(self, commit=True):
        self.instance.languages = split_csv(self.cleaned_data["languages_csv"])
        return super().save(commit)


class InstagramHandleForm(StyledFormMixin, forms.Form):
    handle = forms.RegexField(
        regex=r"^@?[A-Za-z0-9._]{1,30}$",
        label="Instagram username",
        error_messages={"invalid": "Enter a valid Instagram username."},
    )


class RatesForm(StyledFormMixin, forms.ModelForm):
    reel_rupees = forms.IntegerField(label="Fee per Reel (₹)", min_value=300)
    story_rupees = forms.IntegerField(label="Fee per Story (₹)", min_value=100, required=False)
    post_rupees = forms.IntegerField(label="Fee per feed post (₹)", min_value=200, required=False)
    red_lines = forms.MultipleChoiceField(
        choices=SensitiveCategory.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Categories you never want to promote",
    )

    class Meta:
        model = CreatorProfile
        fields = ["allows_ai_likeness", "max_active_campaigns", "on_break"]
        labels = {
            "allows_ai_likeness": "Allow AI-generated content using my face/voice (I still approve every "
            "piece before it's posted)",
            "max_active_campaigns": "Maximum campaigns at the same time",
            "on_break": "I'm on a break (pause new offers)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        self.fields["reel_rupees"].initial = inst.rate_reel // 100 or None
        self.fields["story_rupees"].initial = inst.rate_story // 100 or None
        self.fields["post_rupees"].initial = inst.rate_post // 100 or None
        self.fields["red_lines"].initial = inst.red_lines

    def save(self, commit=True):
        inst = self.instance
        inst.rate_reel = rupees_to_paise(self.cleaned_data["reel_rupees"])
        inst.rate_story = rupees_to_paise(self.cleaned_data.get("story_rupees") or 0)
        inst.rate_post = rupees_to_paise(self.cleaned_data.get("post_rupees") or 0)
        inst.red_lines = self.cleaned_data["red_lines"]
        return super().save(commit)


class KycForm(StyledFormMixin, forms.Form):
    legal_name = forms.CharField(label="Full name as on PAN", max_length=200)
    pan = UpperCharField(label="PAN", max_length=10, validators=[validate_pan])
    gstin = UpperCharField(
        label="GSTIN (only if registered)", max_length=15, required=False, validators=[validate_gstin]
    )
    bank_account_name = forms.CharField(label="Account holder name", max_length=200)
    bank_account_number = forms.RegexField(regex=r"^\d{9,18}$", label="Account number")
    bank_account_number_confirm = forms.CharField(label="Re-enter account number")
    bank_ifsc = UpperCharField(label="IFSC", max_length=11, validators=[validate_ifsc])
    kyc_document = forms.FileField(label="PAN card (photo or PDF)", help_text="JPG, PNG or PDF, up to 5 MB.")

    def clean_kyc_document(self):
        doc = self.cleaned_data["kyc_document"]
        if doc.size > 5 * 1024 * 1024:
            raise forms.ValidationError("File is larger than 5 MB.")
        name = doc.name.lower()
        if not name.endswith((".jpg", ".jpeg", ".png", ".pdf")):
            raise forms.ValidationError("Upload a JPG, PNG or PDF.")
        return doc

    def clean(self):
        cleaned = super().clean()
        a, b = cleaned.get("bank_account_number"), cleaned.get("bank_account_number_confirm")
        if a and b and a != b.strip():
            self.add_error("bank_account_number_confirm", "Account numbers don't match.")
        gstin, pan = cleaned.get("gstin"), cleaned.get("pan")
        if gstin and pan and gstin[2:12] != pan:
            self.add_error("gstin", "This GSTIN doesn't belong to the PAN above.")
        return cleaned
