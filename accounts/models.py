from datetime import timedelta

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)


class User(AbstractUser):
    """A club member, identified by email. Passwords are never used."""

    class Sex(models.TextChoices):
        MALE = "M", _("Male")
        FEMALE = "F", _("Female")

    username = None
    email = models.EmailField(_("email address"), unique=True)
    first_name = models.CharField(_("first name"), max_length=150)
    last_name = models.CharField(_("last name"), max_length=150)
    sex = models.CharField(max_length=1, choices=Sex.choices)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name", "sex"]

    objects = UserManager()

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.get_full_name() or self.email

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        super().save(*args, **kwargs)

    @property
    def is_confirmed(self):
        """True once the user has logged in, i.e. proved to own the email address."""
        return self.last_login is not None

    @property
    def short_name(self):
        return f"{self.first_name[:1]}. {self.last_name}" if self.first_name else self.last_name


class LoginToken(models.Model):
    """A one-time login code plus link, sent by email."""

    VALIDITY = timedelta(days=365)  # a code can still be typed in long after it was mailed
    RESEND_INTERVAL = timedelta(seconds=60)
    MAX_ATTEMPTS = 5
    MAX_DAILY_ATTEMPTS = 20  # wrong codes per user and 24 hours, across all tokens

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_tokens")
    code_hash = models.CharField(max_length=64)
    link_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Login token for {self.user} ({self.created_at:%Y-%m-%d %H:%M})"

    def is_usable(self, now=None):
        now = now or timezone.now()
        return self.used_at is None and now < self.expires_at and self.attempts < self.MAX_ATTEMPTS
