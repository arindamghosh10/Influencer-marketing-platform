from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator

from apps.core import ratelimit
from apps.core.events import record

from .forms import LoginForm, SignupForm

# Failed logins allowed per email address in LOGIN_WINDOW seconds (blocks password guessing on
# one account from many IPs); the per-IP limit below catches one IP trying many accounts.
LOGIN_FAILURES = 5
LOGIN_WINDOW = 15 * 60


@ratelimit.ratelimit("signup", limit=10, window=60 * 60)
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


@method_decorator(ratelimit.ratelimit("login-ip", limit=30, window=LOGIN_WINDOW), name="dispatch")
class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        email = (request.POST.get("username") or "").strip().lower()
        if email and ratelimit.is_blocked(f"login-email:{email}", LOGIN_FAILURES):
            return ratelimit.too_many(request, LOGIN_WINDOW // 60)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        email = (self.request.POST.get("username") or "").strip().lower()
        if email:
            ratelimit.hit(f"login-email:{email}", LOGIN_FAILURES, LOGIN_WINDOW)
        return super().form_invalid(form)

    def form_valid(self, form):
        ratelimit.reset(f"login-email:{form.get_user().email.lower()}")
        return super().form_valid(form)
