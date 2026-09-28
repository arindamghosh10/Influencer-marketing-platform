from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core.forms import StyledFormMixin

from . import services
from .models import ConsentScope


class SignForm(StyledFormMixin, forms.Form):
    signed_name = forms.CharField(label="Type your full legal name to sign", max_length=200)
    accept = forms.BooleanField(label="I have read and agree to this agreement.")


class OtpForm(StyledFormMixin, forms.Form):
    code = forms.CharField(label="6-digit code from your email", max_length=6, min_length=6)


@login_required
def sign(request):
    data = services.pending(request)
    if not data:
        messages.warning(request, "Nothing to sign right now.")
        return redirect("core:home")
    form = SignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        code = services.send_otp(request, form.cleaned_data["signed_name"])
        if settings.DEBUG:
            messages.info(request, f"Development mode: your code is {code} (also printed in the server log).")
        return redirect("contracts:verify")
    scopes = [ConsentScope(s).label for s in data["consents"]]
    return render(request, "contracts/sign.html", {"data": data, "form": form, "scopes": scopes})


@login_required
def verify(request):
    data = services.pending(request)
    if not data or not data.get("otp_id"):
        return redirect("contracts:sign")
    form = OtpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        agreement, error = services.verify_and_sign(request, form.cleaned_data["code"])
        if agreement:
            messages.success(request, "Signed. A copy is saved in your account.")
            return redirect(data["next_url"])
        form.add_error("code", error)
    return render(request, "contracts/verify.html", {"form": form, "email": request.user.email})


@login_required
@require_POST
def resend(request):
    if services.pending(request):
        data = services.pending(request)
        code = services.send_otp(request, data.get("signed_name", ""))
        if settings.DEBUG:
            messages.info(request, f"Development mode: your new code is {code}.")
        else:
            messages.info(request, "We sent a new code.")
    return redirect("contracts:verify")


@login_required
def consents(request):
    current = services.current_consents(request.user)
    rows = []
    for scope in ConsentScope:
        event = current.get(scope.value)
        rows.append(
            {
                "scope": scope,
                "event": event,
                "granted": bool(event and event.action == "granted"),
                "revocable": scope in services.REVOCABLE,
            }
        )
    agreements = request.user.agreements.all()
    return render(request, "contracts/consents.html", {"rows": rows, "agreements": agreements})


@login_required
@require_POST
def toggle_consent(request, scope):
    if scope not in {s.value for s in services.REVOCABLE}:
        messages.error(request, "This consent is part of a signed agreement and can't be toggled here.")
        return redirect("contracts:consents")
    granted = request.POST.get("grant") == "1"
    services.set_consent(request, scope, granted)
    messages.success(request, "Your consent settings were updated.")
    return redirect("contracts:consents")


@login_required
def agreement_detail(request, pk):
    agreement = request.user.agreements.get(pk=pk)
    return render(request, "contracts/agreement_detail.html", {"agreement": agreement})
