"""Django settings for Klubliga.

All deployment-specific values come from environment variables, see README.md.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "django-insecure-dev-key-change-me-in-production"
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "league",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "league.context_processors.league",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DJANGO_DB_PATH", BASE_DIR / "db.sqlite3"),
    }
}

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "league:home"
# Password-less login: keep devices logged in for a year.
SESSION_COOKIE_AGE = 365 * 24 * 60 * 60

# The interface is German; the source strings are English (see locale/).
LANGUAGE_CODE = "de"
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Europe/Berlin")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# WhiteNoise serves the collected static files. In production they are
# compressed and get hashed file names (requires `collectstatic`).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email: SMTP when EMAIL_HOST is set, console output otherwise.
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "klubliga@localhost")
if os.environ.get("EMAIL_HOST"):
    if os.environ.get("LOCAL_ENV", "0") == "1":
        email_backend = "accounts.email_backend.LocalSMTPEmailBackend"
    else:
        email_backend = "django.core.mail.backends.smtp.EmailBackend"

    MAILERS = {
        "default": {
            "BACKEND": email_backend,
            "OPTIONS": {
                "host": os.environ["EMAIL_HOST"],
                "port": int(os.environ.get("EMAIL_PORT", "465")),
                "username": os.environ.get("EMAIL_HOST_USER", ""),
                "password": os.environ.get("EMAIL_HOST_PASSWORD", ""),
                "use_ssl": os.environ.get("EMAIL_USE_SSL", "1") == "1",
                "use_tls": os.environ.get("EMAIL_USE_TLS", "0") == "1",
            },
        },
    }
else:
    MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
