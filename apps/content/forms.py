from django import forms
from django.utils import timezone

from apps.core.forms import StyledFormMixin


class DraftForm(StyledFormMixin, forms.Form):
    file = forms.FileField(
        label="Video or image", help_text="MP4 or MOV for Reels; JPG/PNG allowed for posts and stories."
    )
    caption = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 5}),
        max_length=2200,
        help_text="Must include a disclosure such as '#ad' or 'Paid partnership with …'.",
    )


class ReviewForm(StyledFormMixin, forms.Form):
    decision = forms.ChoiceField(choices=[("approved", "Approve"), ("changes", "Request changes")])
    comment = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), required=False, label="Feedback for the creator"
    )


class FinalApprovalForm(StyledFormMixin, forms.Form):
    publish_at = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        label="Go live at",
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    auto_publish = forms.BooleanField(
        required=False,
        initial=True,
        label="Publish it for me automatically at that time",
        help_text="Untick to post it yourself and paste the link afterwards.",
    )
    confirm = forms.BooleanField(label="I approve this exact video and caption for my Instagram account.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["publish_at"].initial = (timezone.localtime() + timezone.timedelta(minutes=10)).strftime(
            "%Y-%m-%dT%H:%M"
        )


class SelfPostForm(StyledFormMixin, forms.Form):
    permalink = forms.URLField(
        label="Link to your post", assume_scheme="https", help_text="Instagram → your post → ⋯ → Copy link"
    )

    def clean_permalink(self):
        url = self.cleaned_data["permalink"]
        if "instagram.com/" not in url:
            raise forms.ValidationError("Paste an instagram.com link to the post.")
        return url
