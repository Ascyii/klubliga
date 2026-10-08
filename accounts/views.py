from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _

from . import services
from .forms import CodeForm, EmailForm, RegistrationForm
from .models import User

SESSION_EMAIL = "login_email"
SESSION_NEXT = "login_next"


def _remember_next(request):
    next_url = request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
        request.session[SESSION_NEXT] = next_url


def _finish_login(request, user):
    next_url = request.session.pop(SESSION_NEXT, None)
    request.session.pop(SESSION_EMAIL, None)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    messages.success(request, _("Welcome, %(name)s!") % {"name": user.first_name})
    return redirect(next_url or "league:home")


def _send_code(request, user):
    request.session[SESSION_EMAIL] = user.email
    if services.request_login(request, user):
        messages.info(request, _("We sent a login code to %(email)s.") % {"email": user.email})
    else:
        messages.warning(request, _("A code was sent less than a minute ago – please check your inbox."))
    return redirect("accounts:code")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("league:home")
    _remember_next(request)
    form = EmailForm(request.POST or None, initial={"email": request.GET.get("email", "")})
    if form.is_valid():
        email = form.cleaned_data["email"]
        user = User.objects.filter(email=email).first()
        if user is None or not user.is_active:
            if user is None:
                messages.info(request, _("No account with this address yet – please register."))
                return redirect(f"{reverse('accounts:register')}?{urlencode({'email': email})}")
            form.add_error("email", _("This account is disabled."))
        else:
            return _send_code(request, user)
    return render(request, "accounts/login.html", {"form": form})


def register_view(request):
    if request.user.is_authenticated:
        return redirect("league:home")
    instance = None
    if request.method == "POST":
        # An unconfirmed registration may be repeated (e.g. after a typo in the name).
        instance = User.objects.filter(
            email=request.POST.get("email", "").strip().lower(), last_login__isnull=True
        ).first()
    form = RegistrationForm(
        request.POST or None, instance=instance, initial={"email": request.GET.get("email", "")}
    )
    if form.is_valid():
        user = form.save(commit=False)
        if user.pk is None:
            user.set_unusable_password()
        user.save()
        return _send_code(request, user)
    return render(request, "accounts/register.html", {"form": form})


def code_view(request):
    email = request.session.get(SESSION_EMAIL)
    user = User.objects.filter(email=email, is_active=True).first() if email else None
    if user is None:
        return redirect("accounts:login")
    form = CodeForm(request.POST or None)
    if form.is_valid():
        if services.verify_code(user, form.cleaned_data["code"]):
            return _finish_login(request, user)
        form.add_error("code", _("This code is wrong or has expired."))
    return render(request, "accounts/code.html", {"form": form, "email": email})


def resend_view(request):
    email = request.session.get(SESSION_EMAIL)
    user = User.objects.filter(email=email, is_active=True).first() if email else None
    if request.method != "POST" or user is None:
        return redirect("accounts:login")
    return _send_code(request, user)


def link_view(request, secret):
    token = services.find_link_token(secret)
    if token is None or not token.user.is_active:
        messages.error(request, _("This login link is invalid or has expired. Please request a new code."))
        return redirect("accounts:login")
    if request.method == "POST":
        services.consume_token(token)
        return _finish_login(request, token.user)
    return render(request, "accounts/link.html", {"login_user": token.user})


logout_view = LogoutView.as_view(next_page="accounts:login")
