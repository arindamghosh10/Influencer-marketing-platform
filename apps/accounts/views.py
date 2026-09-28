from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from apps.core.events import record

from .forms import LoginForm, SignupForm


def signup(request):
    if request.user.is_authenticated:
        return redirect("core:home")
    form = SignupForm(request.POST or None, initial={"role": request.GET.get("role")})
    if request.method == "POST" and form.is_valid():
        user = form.save()
        record(
            "account.created",
            f"{user.get_role_display()} account created",
            actor=user,
            target=user,
            request=request,
        )
        login(request, user)
        return redirect("core:home")
    return render(request, "accounts/signup.html", {"form": form})


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True
