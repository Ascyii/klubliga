"""Password-less login: issuing, sending and checking one-time tokens."""

import hashlib
import secrets

from django.core.mail import send_mail
from django.db.models import F
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from .models import LoginToken


def hash_secret(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def issue_login_token(user, now=None):
    """Create a new token for ``user`` and return ``(code, link_secret)``.

    Returns ``None`` if a still valid token was issued less than
    ``LoginToken.RESEND_INTERVAL`` ago. Issuing a token invalidates all older ones.
    """
    now = now or timezone.now()
    latest = user.login_tokens.first()
    if latest and latest.is_usable(now) and now - latest.created_at < LoginToken.RESEND_INTERVAL:
        return None
    user.login_tokens.filter(used_at__isnull=True, expires_at__gt=now).update(expires_at=now)
    code = f"{secrets.randbelow(10**6):06d}"
    link_secret = secrets.token_urlsafe(32)
    LoginToken.objects.create(
        user=user,
        code_hash=hash_secret(code),
        link_hash=hash_secret(link_secret),
        created_at=now,
        expires_at=now + LoginToken.VALIDITY,
    )
    return code, link_secret


def send_login_email(request, user, code, link_secret):
    link = request.build_absolute_uri(reverse("accounts:link", args=[link_secret]))
    context = {"user": user, "code": code, "link": link,
               "minutes": int(LoginToken.VALIDITY.total_seconds() // 60)}
    subject = render_to_string("accounts/login_email_subject.txt", context, request).strip()
    body = render_to_string("accounts/login_email.txt", context, request)
    send_mail(subject, body, None, [user.email])


def request_login(request, user):
    """Issue a token and email it. Returns False if one was sent very recently."""
    issued = issue_login_token(user)
    if issued is None:
        return False
    send_login_email(request, user, *issued)
    return True


def verify_code(user, code, now=None):
    """Check ``code`` against the user's newest token; consume it on success."""
    now = now or timezone.now()
    token = user.login_tokens.first()
    if token is None or not token.is_usable(now):
        return False
    if constant_time_compare(hash_secret(code.strip()), token.code_hash):
        token.used_at = now
        token.save(update_fields=["used_at"])
        return True
    LoginToken.objects.filter(pk=token.pk).update(attempts=F("attempts") + 1)
    return False


def find_link_token(link_secret, now=None):
    """Return the usable token belonging to an emailed link, or None."""
    token = (
        LoginToken.objects.select_related("user")
        .filter(link_hash=hash_secret(link_secret))
        .first()
    )
    if token is None or not token.is_usable(now):
        return None
    if token.user.login_tokens.first() != token:  # superseded by a newer token
        return None
    return token


def consume_token(token, now=None):
    token.used_at = now or timezone.now()
    token.save(update_fields=["used_at"])
