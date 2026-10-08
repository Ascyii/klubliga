from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from league import services
from league.forms import EntryForm, ResultForm, SeasonForm
from league.models import Entry, Match, Season

from .helpers import group_match, make_season, make_user, place, play_round_robin, singles, win


class AccessTests(TestCase):
    def test_login_required(self):
        for name in ["home", "matches", "groups", "settings"]:
            response = self.client.get(reverse(f"league:{name}"))
            self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse(f'league:{name}')}",
                                 fetch_redirect_response=False)

    def test_admin_pages_forbidden_for_players(self):
        self.client.force_login(make_user())
        for name in ["groups", "settings"]:
            self.assertEqual(self.client.get(reverse(f"league:{name}")).status_code, 403)
        self.assertEqual(self.client.post(reverse("league:close"), {"scope": "all"}).status_code, 403)

    def test_title_bar_shows_league_and_season(self):
        user = make_user("Hanna", "Wolf", "F")
        self.client.force_login(user)
        response = self.client.get(reverse("league:home"))
        season = Season.current()
        self.assertContains(response, f'<span class="season">{season.year}</span>', html=True)
        self.assertContains(response, "Hanna Wolf")
        self.assertNotContains(response, reverse("league:groups"))


class HomeTests(TestCase):
    def setUp(self):
        self.season = make_season()
        self.user = make_user("Max", "Muster", "M")
        self.client.force_login(self.user)

    def test_create_singles_entry(self):
        response = self.client.post(reverse("league:home"), {"kind": "singles"}, follow=True)
        self.assertContains(response, "Du bist für Herreneinzel gemeldet")
        entry = Entry.objects.get()
        self.assertEqual((entry.player1, entry.player2, entry.tournament), (self.user, None, "MS"))
        self.assertContains(response, "Gemeldet")

    def test_create_doubles_entry(self):
        partner = make_user("Eva", "Partner", "F")
        self.client.post(reverse("league:home"), {"kind": "doubles", "partner": partner.pk})
        self.assertEqual(Entry.objects.get().tournament, "XD")

    def test_doubles_requires_partner_and_duplicate_is_rejected(self):
        response = self.client.post(reverse("league:home"), {"kind": "doubles"})
        self.assertContains(response, "Bitte wähle deine Partnerin oder deinen Partner.")
        services.create_entry(self.season, self.user)
        response = self.client.post(reverse("league:home"), {"kind": "singles"})
        self.assertContains(response, "bereits für")
        self.assertEqual(Entry.objects.count(), 1)

    def test_partner_choices_only_confirmed_members(self):
        confirmed = make_user("Yes", sex="F")
        unconfirmed = make_user("No", sex="F", confirmed=False)
        partners = list(EntryForm(user=self.user).fields["partner"].queryset)
        self.assertIn(confirmed, partners)
        self.assertNotIn(unconfirmed, partners)
        self.assertNotIn(self.user, partners)
        html = str(EntryForm(user=self.user)["partner"])
        self.assertIn('data-sex="F"', html)

    def test_home_shows_groups_and_matches(self):
        mine = services.create_entry(self.season, self.user)
        others = singles(self.season, 2)
        place(self.season, [mine, *others], "A")
        response = self.client.get(reverse("league:home"))
        self.assertContains(response, "Meine Gruppen")
        self.assertContains(response, "2 offen")
        self.assertContains(response, 'class="me"')

    def test_withdraw(self):
        entry = services.create_entry(self.season, self.user)
        response = self.client.post(reverse("league:withdraw", args=[entry.pk]), follow=True)
        self.assertContains(response, "wurde zurückgezogen")
        entry.refresh_from_db()
        self.assertFalse(entry.is_active)
        response = self.client.post(reverse("league:withdraw", args=[entry.pk]), follow=True)
        self.assertContains(response, "bereits zurückgezogen")

    def test_withdraw_foreign_entry_forbidden(self):
        other = singles(self.season, 1)[0]
        self.assertEqual(self.client.post(reverse("league:withdraw", args=[other.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("league:withdraw", args=[other.pk])).status_code, 405)


class MatchDetailTests(TestCase):
    def setUp(self):
        self.season = make_season(started=True)
        self.a, self.b, self.c = singles(self.season, 3)
        place(self.season, [self.a, self.b, self.c], "A")
        self.match = group_match(self.a, self.b)
        self.url = reverse("league:match", args=[self.match.pk])

    def test_participant_enters_result(self):
        self.client.force_login(self.a.player1)
        response = self.client.get(self.url)
        self.assertContains(response, "<score-input")
        self.assertContains(response, self.b.player1.email)
        self.assertContains(response, "Match-Tiebreak")
        response = self.client.post(self.url, {"s1_1": 6, "s1_2": 3, "s2_1": 3, "s2_2": 6, "s3_1": 10, "s3_2": 4},
                                    follow=True)
        self.assertContains(response, "Das Ergebnis wurde gespeichert.")
        self.match.refresh_from_db()
        self.assertEqual((self.match.score, self.match.winner), ("6:3 3:6 10:4", self.match.entry1))

    def test_invalid_result_shows_error(self):
        self.client.force_login(self.a.player1)
        response = self.client.post(self.url, {"s1_1": 6, "s1_2": 3})
        self.assertContains(response, "Das Match ist nicht beendet")
        response = self.client.post(self.url, {"s1_1": 6, "s2_1": 6, "s2_2": 2})
        self.assertContains(response, "Satz 1: Bitte gib das Ergebnis beider Seiten ein.")
        response = self.client.post(self.url, {"s1_1": 6, "s1_2": 3, "s3_1": 6, "s3_2": 2})
        self.assertContains(response, "Bitte trage die Sätze der Reihe nach ein.")
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.PENDING)

    def test_non_participant_cannot_edit(self):
        self.client.force_login(self.c.player1)
        response = self.client.get(self.url)
        self.assertNotContains(response, "<score-input")
        self.assertEqual(self.client.post(self.url, {"s1_1": 6}).status_code, 403)

    def test_lock_reason_before_start(self):
        self.season.started_at = None
        self.season.save()
        self.client.force_login(self.a.player1)
        self.assertContains(self.client.get(self.url), "sobald die Liga begonnen hat")

    def test_admin_records_walkover_and_cancel(self):
        self.client.force_login(make_user(is_staff=True))
        self.assertContains(self.client.get(self.url), "Nicht gespielt")
        self.client.post(self.url, {"outcome": "w2"})
        self.match.refresh_from_db()
        self.assertEqual((self.match.status, self.match.winner), (Match.Status.WALKOVER, self.match.entry2))
        self.client.post(self.url, {"outcome": "cancelled"})
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.CANCELLED)
        self.client.post(self.url, {"outcome": "pending"})
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.PENDING)
        response = self.client.post(f"{self.url}?next=/matches/", {"outcome": "played", "s1_1": 6, "s1_2": 0, "s2_1": 6, "s2_2": 0})
        self.assertRedirects(response, "/matches/", fetch_redirect_response=False)

    def test_admin_knockout_form_has_no_cancel(self):
        play_round_robin([self.a, self.b, self.c])
        final = Match.objects.get(stage="final")
        form = ResultForm(match=final, admin=True)
        self.assertNotIn("cancelled", dict(form.fields["outcome"].choices))

    def test_result_form_prefills_score(self):
        services.record_result(self.match, [(7, 6), (6, 4)], None)
        self.match.refresh_from_db()
        form = ResultForm(match=self.match)
        self.assertEqual((form.initial["s1_1"], form.initial["s2_2"]), (7, 4))
        self.assertEqual([r["label"] for r in form.set_rows()], ["Satz 1", "Satz 2", "Match-Tiebreak"])


class MatchesPageTests(TestCase):
    def setUp(self):
        self.season = make_season(started=True)
        self.user = make_user()
        self.client.force_login(self.user)
        self.a = singles(self.season, 3, prefix="Alpha")
        self.b = singles(self.season, 3, prefix="Bravo")
        place(self.season, self.a, "A")
        place(self.season, self.b, "B")
        play_round_robin(self.a)

    def test_standings_bracket_and_list(self):
        response = self.client.get(reverse("league:matches"), {"t": "MS"})
        self.assertContains(response, "Gruppe A")
        self.assertContains(response, "beendet")
        self.assertContains(response, "Sieger Gruppe A – Zweiter Gruppe B")
        self.assertEqual(len(response.context["match_list"]), 6)

    def test_filters(self):
        url = reverse("league:matches")
        self.assertEqual(len(self.client.get(url, {"t": "MS", "stage": "A"}).context["match_list"]), 3)
        self.assertEqual(len(self.client.get(url, {"t": "MS", "status": "open"}).context["match_list"]), 3)
        self.assertEqual(len(self.client.get(url, {"t": "MS", "status": "done"}).context["match_list"]), 3)
        self.assertEqual(len(self.client.get(url, {"t": "MS", "q": "bravo01"}).context["match_list"]), 2)
        self.assertEqual(len(self.client.get(url, {"t": "MS", "mine": "1"}).context["match_list"]), 0)
        self.assertEqual(len(self.client.get(url, {"t": "MS", "stage": "ko"}).context["match_list"]), 0)

    def test_default_tournament_and_other_season(self):
        response = self.client.get(reverse("league:matches"))
        self.assertEqual(response.context["tournament"], "MS")
        old = Season.objects.create(year=self.season.year - 1)
        response = self.client.get(reverse("league:matches"), {"season": old.year, "t": "WD"})
        self.assertEqual(response.context["view_season"], old)
        self.assertContains(response, "wurden keine Gruppen gebildet")
        self.assertFalse(response.context["can_manage"])

    def test_remembers_last_tournament(self):
        url = reverse("league:matches")
        self.client.get(url, {"t": "XD"})
        self.assertEqual(self.client.get(url).context["tournament"], "XD")
        self.assertEqual(self.client.get(url, {"t": "WS"}).context["tournament"], "WS")
        self.assertEqual(self.client.get(url).context["tournament"], "WS")

    def test_admin_closes_group_and_tournament(self):
        admin = make_user(is_staff=True)
        self.client.force_login(admin)
        response = self.client.get(reverse("league:matches"), {"t": "MS"})
        self.assertContains(response, "Gruppenphase des Wettbewerbs abschließen")
        group_b = self.b[0].group
        response = self.client.post(reverse("league:close"), {"scope": "group", "group": group_b.pk}, follow=True)
        self.assertContains(response, "3 offene Matches als nicht gespielt markiert")
        self.assertEqual(Match.objects.filter(stage="semi").count(), 2)
        response = self.client.post(reverse("league:close"), {"scope": "tournament", "tournament": "MS"}, follow=True)
        self.assertContains(response, "0 offene Matches")
        self.assertEqual(self.client.post(reverse("league:close"), {"scope": "bogus"}).status_code, 403)


class AdminPageTests(TestCase):
    def setUp(self):
        self.season = make_season()
        self.client.force_login(make_user(is_staff=True))
        self.entries = singles(self.season, 4)

    def test_groups_page_manual_assignment(self):
        url = reverse("league:groups")
        response = self.client.get(url, {"t": "MS"})
        self.assertContains(response, "Herreneinzel (4)")
        self.assertContains(response, "Vorschlag: 1 Gruppe.")
        data = {"action": "save", **{f"entry-{e.pk}": "A" for e in self.entries[:3]}, f"entry-{self.entries[3].pk}": "B"}
        response = self.client.post(f"{url}?t=MS", data, follow=True)
        self.assertContains(response, "Gruppen gespeichert (4 Änderungen).")
        self.assertEqual(Match.objects.count(), 3)

    def test_groups_page_random_split_and_remove(self):
        url = reverse("league:groups")
        self.client.post(f"{url}?t=MS", {"action": "random2"})
        self.assertEqual(Entry.objects.filter(group__isnull=False).count(), 4)
        win(Match.objects.first(), Match.objects.first().entry1)
        response = self.client.post(f"{url}?t=MS", {"action": "random1"}, follow=True)
        self.assertContains(response, "zufällige Einteilung ist nicht mehr möglich")
        entry = self.entries[0]
        response = self.client.post(f"{reverse('league:withdraw', args=[entry.pk])}?next={url}%3Ft%3DMS", follow=True)
        self.assertEqual(response.redirect_chain[-1][0], f"{url}?t=MS")
        entry.refresh_from_db()
        self.assertFalse(entry.is_active)
        self.assertContains(response, "Zurückgezogen")

    def test_settings_save_start_and_close_all(self):
        url = reverse("league:settings")
        self.assertContains(self.client.get(url), "Liga starten")
        data = {"action": "save", "name": "Sommerliga", "best_of": 3, "games_per_set": 4,
                "deciding_match_tiebreak": "on", "match_tiebreak_points": 7, "two_groups_from": 6}
        self.client.post(url, data)
        self.season.refresh_from_db()
        self.assertEqual((self.season.name, self.season.games_per_set), ("Sommerliga", 4))
        response = self.client.post(url, {**data, "games_per_set": 12})
        self.assertContains(response, "kleiner oder gleich 9")
        response = self.client.post(url, {"action": "start"}, follow=True)
        self.assertContains(response, "Die Liga hat begonnen")
        response = self.client.post(url, {"action": "start"}, follow=True)
        self.assertContains(response, "bereits begonnen")
        place(self.season, self.entries[:2], "A")
        response = self.client.post(reverse("league:close"), {"scope": "all", "next": url}, follow=True)
        self.assertContains(response, "1 offenes Match")
        self.assertContains(response, "angesetzt")

    def test_season_form_limits(self):
        form = SeasonForm({"name": "X", "best_of": 2, "games_per_set": 6, "match_tiebreak_points": 10,
                           "two_groups_from": 8}, instance=self.season)
        self.assertIn("best_of", form.errors)


class DemoCommandTests(TestCase):
    def test_demo_fills_season(self):
        out = StringIO()
        call_command("demo", seed=7, results=1.0, stdout=out)
        season = Season.current()
        self.assertTrue(season.is_started)
        self.assertEqual(Entry.objects.filter(season=season, group__isnull=True).count(), 1)
        self.assertFalse(Match.objects.filter(stage="group", status="pending").exists())
        self.assertTrue(Match.objects.filter(stage="final").exists())
        self.assertIn("results", out.getvalue())
        with self.assertRaises(Exception):
            call_command("demo", stdout=out)
        call_command("demo", reset=True, seed=1, stdout=out)
