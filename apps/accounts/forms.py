from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password

from apps.core.forms import StyledFormMixin

from .models import User


class SignupForm(StyledFormMixin, forms.Form):
    role = forms.ChoiceField(
        choices=[(User.Role.BRAND, "I'm a brand"), (User.Role.CREATOR, "I'm a creator")],
        widget=forms.RadioSelect,
    )
    name = forms.CharField(max_length=120, label="Your name")
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password"):
            validate_password(cleaned["password"])
        return cleaned

    def save(self):
        first, _, last = self.cleaned_data["name"].partition(" ")
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
            role=self.cleaned_data["role"],
            first_name=first,
            last_name=last,
        )


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.EmailField(label="Email")
