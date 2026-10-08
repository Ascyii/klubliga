import re

from django.conf import settings
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.models import User

SOURCE_LANGUAGE = "en"  # the texts in code and templates


class LanguageTests(TestCase):
    def choose(self, language):
        return self.client.post(reverse("set_language"), {"language": language, "next": reverse("accounts:login")})

    def test_german_is_the_default_whatever_the_browser_prefers(self):
        response = self.client.get(reverse("accounts:login"), headers={"accept-language": "en-US,en;q=0.9"})
        self.assertContains(response, '<html lang="de">')
        self.assertContains(response, "Anmeldecode senden")
        self.assertEqual(response["Content-Language"], "de")

    def test_switch_to_english_and_back(self):
        response = self.choose("en")
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME]["max-age"], settings.LANGUAGE_COOKIE_AGE)
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, '<html lang="en">')
        self.assertContains(response, "Send login code")
        self.choose("de")
        self.assertContains(self.client.get(reverse("accounts:login")), "Anmeldecode senden")

    def test_unsupported_language_falls_back_to_default(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "fr"
        self.assertContains(self.client.get(reverse("accounts:login")), '<html lang="de">')

    def test_switch_is_offered_for_every_language(self):
        response = self.client.get(reverse("accounts:login"))
        for code, _ in settings.LANGUAGES:
            self.assertContains(response, f'name="language" value="{code}"')

    def test_login_email_uses_the_chosen_language(self):
        User.objects.create_user("anna@example.com", first_name="Anna", last_name="Meier", sex="F")
        self.choose("en")
        self.client.post(reverse("accounts:login"), {"email": "anna@example.com"})
        self.assertIn("Hello Anna", mail.outbox[-1].body)
        self.assertTrue(re.search(r"your login code \d{6}", mail.outbox[-1].subject))

    def test_every_language_has_a_compiled_catalogue(self):
        for code, _ in settings.LANGUAGES:
            if code != SOURCE_LANGUAGE:
                catalogue = settings.BASE_DIR / "locale" / code / "LC_MESSAGES" / "django.mo"
                self.assertTrue(catalogue.exists(), f"{catalogue} is missing – run `just messages`")
