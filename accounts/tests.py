import re
from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.management import CommandError, call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import LoginToken, User


def make_user(email="anna@example.com", confirmed=False, **extra):
    user = User.objects.create_user(email=email, first_name="Anna", last_name="Meier", sex="F", **extra)
    if confirmed:
        user.last_login = timezone.now()
        user.save()
    return user


class UserModelTests(TestCase):
    def test_create_user(self):
        user = User.objects.create_user(email="Max@Example.COM", first_name="Max", last_name="Muster", sex="M")
        self.assertEqual(user.email, "max@example.com")
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_confirmed)
        self.assertEqual(str(user), "Max Muster")
        self.assertEqual(user.short_name, "M. Muster")
        self.assertEqual(User.objects.get_by_natural_key("MAX@example.com"), user)

    def test_create_superuser(self):
        admin = User.objects.create_superuser(email="boss@example.com", password="x",
                                              first_name="B", last_name="Oss", sex="F")
        self.assertTrue(admin.is_staff and admin.is_superuser)

    def test_email_required(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", first_name="A", last_name="B", sex="M")


class TokenServiceTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_issue_and_verify_code(self):
        code, link = services.issue_login_token(self.user)
        self.assertRegex(code, r"^\d{6}$")
        self.assertTrue(len(link) > 30)
        token = LoginToken.objects.get()
        self.assertNotEqual(token.code_hash, code)  # stored hashed
        self.assertFalse(services.verify_code(self.user, "000000" if code != "000000" else "111111"))
        self.assertTrue(services.verify_code(self.user, f" {code} "))
        self.assertFalse(services.verify_code(self.user, code))  # single use

    def test_rate_limit_and_newest_only(self):
        now = timezone.now()
        first = services.issue_login_token(self.user, now=now)
        self.assertIsNone(services.issue_login_token(self.user, now=now + timedelta(seconds=30)))
        second = services.issue_login_token(self.user, now=now + timedelta(seconds=61))
        self.assertIsNotNone(second)
        self.assertFalse(services.verify_code(self.user, first[0]) and first[0] != second[0])
        self.assertIsNone(services.find_link_token(first[1]))
        self.assertIsNotNone(services.find_link_token(second[1]))

    def test_attempts_limit(self):
        code, _ = services.issue_login_token(self.user)
        wrong = "123456" if code != "123456" else "654321"
        for _ in range(LoginToken.MAX_ATTEMPTS):
            self.assertFalse(services.verify_code(self.user, wrong))
        self.assertFalse(services.verify_code(self.user, code))

    def test_daily_attempts_limit(self):
        now = timezone.now()
        for minute in range(LoginToken.MAX_DAILY_ATTEMPTS // LoginToken.MAX_ATTEMPTS):
            code, _ = services.issue_login_token(self.user, now=now + timedelta(minutes=minute))
            wrong = "123456" if code != "123456" else "654321"
            for _ in range(LoginToken.MAX_ATTEMPTS):
                services.verify_code(self.user, wrong, now=now + timedelta(minutes=minute))
        later = now + timedelta(minutes=30)
        code, _ = services.issue_login_token(self.user, now=later)
        self.assertFalse(services.verify_code(self.user, code, now=later))
        tomorrow = now + timedelta(days=1, minutes=10)
        code, _ = services.issue_login_token(self.user, now=tomorrow)
        self.assertTrue(services.verify_code(self.user, code, now=tomorrow))

    def test_expiry(self):
        code, link = services.issue_login_token(self.user)
        later = timezone.now() + LoginToken.VALIDITY + timedelta(seconds=1)
        self.assertFalse(services.verify_code(self.user, code, now=later))
        self.assertIsNone(services.find_link_token(link, now=later))

    def test_link_token_consumed(self):
        _, link = services.issue_login_token(self.user)
        token = services.find_link_token(link)
        self.assertEqual(token.user, self.user)
        services.consume_token(token)
        self.assertIsNone(services.find_link_token(link))
        self.assertIsNone(services.find_link_token("unknown"))

    def test_email_content(self):
        request = RequestFactory().get("/")
        self.assertTrue(services.request_login(request, self.user))
        self.assertFalse(services.request_login(request, self.user))  # too soon
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["anna@example.com"])
        code = re.search(r"\b(\d{6})\b", message.body).group(1)
        self.assertIn(code, message.subject)
        self.assertIn("http://testserver/login/link/", message.body)
        self.assertIn("Hallo Anna", message.body)


class LoginFlowTests(TestCase):
    def code_from_mail(self):
        return re.search(r"^\s+(\d{6})$", mail.outbox[-1].body, re.M).group(1)

    def link_from_mail(self):
        return re.search(r"(/login/link/[^/\s]+/)", mail.outbox[-1].body).group(1)

    def test_unknown_email_redirects_to_registration(self):
        response = self.client.post(reverse("accounts:login"), {"email": "new@example.com"})
        self.assertRedirects(response, f"{reverse('accounts:register')}?email=new%40example.com")
        response = self.client.get(response["Location"])
        self.assertContains(response, 'value="new@example.com"')

    def test_register_and_login_with_code(self):
        response = self.client.post(reverse("accounts:register"), {
            "email": "New@Example.com", "first_name": "Nora", "last_name": "Neu", "sex": "F",
        })
        self.assertRedirects(response, reverse("accounts:code"))
        user = User.objects.get(email="new@example.com")
        self.assertFalse(user.is_confirmed)
        self.assertContains(self.client.get(reverse("accounts:code")), "new@example.com")
        response = self.client.post(reverse("accounts:code"), {"code": "000000"})
        if "wrong" not in response.content.decode():  # the random code happened to be 000000
            return
        self.assertContains(response, "Dieser Code ist falsch oder abgelaufen.")
        response = self.client.post(reverse("accounts:code"), {"code": self.code_from_mail()})
        self.assertRedirects(response, reverse("league:home"))
        user.refresh_from_db()
        self.assertTrue(user.is_confirmed)
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 302)

    def test_register_twice_before_confirmation_updates_names(self):
        data = {"email": "x@example.com", "first_name": "Typo", "last_name": "Name", "sex": "M"}
        self.client.post(reverse("accounts:register"), data)
        self.client.post(reverse("accounts:register"), {**data, "first_name": "Fixed"})
        self.assertEqual(User.objects.get().first_name, "Fixed")

    def test_register_confirmed_email_is_rejected(self):
        make_user(confirmed=True)
        response = self.client.post(reverse("accounts:register"), {
            "email": "anna@example.com", "first_name": "A", "last_name": "B", "sex": "F"})
        self.assertContains(response, "bereits registriert")

    def test_login_with_link_and_next(self):
        user = make_user(confirmed=True)
        self.client.get(reverse("accounts:login"), {"next": "/matches/"})
        self.client.post(reverse("accounts:login"), {"email": "ANNA@example.com"})
        link = self.link_from_mail()
        response = self.client.get(link)
        self.assertContains(response, "Weiter als")
        self.assertNotIn("_auth_user_id", self.client.session)  # GET does not log in
        response = self.client.post(link)
        self.assertRedirects(response, "/matches/", fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        response = self.client.get(link, follow=True)
        self.assertContains(response, "ungültig oder abgelaufen")

    def test_unsafe_next_is_ignored(self):
        make_user(confirmed=True)
        self.client.get(reverse("accounts:login"), {"next": "https://evil.example.com/"})
        self.client.post(reverse("accounts:login"), {"email": "anna@example.com"})
        response = self.client.post(reverse("accounts:code"), {"code": self.code_from_mail()})
        self.assertRedirects(response, reverse("league:home"), fetch_redirect_response=False)

    def test_resend_and_rate_limit_message(self):
        make_user(confirmed=True)
        self.client.post(reverse("accounts:login"), {"email": "anna@example.com"})
        response = self.client.post(reverse("accounts:resend"), follow=True)
        self.assertContains(response, "weniger als einer Minute")
        self.assertEqual(len(mail.outbox), 1)

    def test_code_page_without_email_redirects(self):
        self.assertRedirects(self.client.get(reverse("accounts:code")), reverse("accounts:login"))
        self.assertRedirects(self.client.get(reverse("accounts:resend")), reverse("accounts:login"))

    def test_inactive_user_cannot_log_in(self):
        make_user(is_active=False)
        response = self.client.post(reverse("accounts:login"), {"email": "anna@example.com"})
        self.assertContains(response, "deaktiviert")
        self.assertEqual(len(mail.outbox), 0)

    def test_logout(self):
        self.client.force_login(make_user(confirmed=True))
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_django_admin_uses_app_login(self):
        response = self.client.get("/django-admin/")
        self.assertEqual(response.status_code, 302)
        response = self.client.get(response["Location"])
        self.assertRedirects(response, "/login/?next=/django-admin/", fetch_redirect_response=False)
        staff = make_user("staff@example.com", is_staff=True)
        self.client.force_login(staff)
        self.assertRedirects(self.client.get("/django-admin/login/?next=/django-admin/"), "/django-admin/")
        self.client.force_login(make_user(confirmed=True))
        self.assertEqual(self.client.get("/django-admin/login/").status_code, 403)
        self.client.force_login(make_user("boss@example.com", is_staff=True, is_superuser=True))
        self.assertEqual(self.client.get("/django-admin/").status_code, 200)
        self.assertEqual(self.client.get("/django-admin/accounts/user/").status_code, 200)
        self.assertEqual(self.client.get("/django-admin/league/match/").status_code, 200)


class SetAdminCommandTests(TestCase):
    def test_grant_and_revoke(self):
        user = make_user()
        out = StringIO()
        call_command("setadmin", "ANNA@example.com", stdout=out)
        user.refresh_from_db()
        self.assertTrue(user.is_staff and user.is_superuser)
        self.assertIn("now an admin", out.getvalue())
        call_command("setadmin", "anna@example.com", "--remove", stdout=out)
        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        with self.assertRaises(CommandError):
            call_command("setadmin", "nobody@example.com")
