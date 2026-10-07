from datetime import date
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from league import services
from league.models import Entry, Match, Season, Tournament
from league.scoring import ScoringRules

from .helpers import group_match, make_season, make_user, place, singles, win


class SeasonTests(TestCase):
    def test_current_is_created_once_for_this_year(self):
        season = Season.current()
        self.assertEqual(season.year, timezone.localdate().year)
        self.assertEqual(Season.current(), season)
        self.assertEqual(Season.objects.count(), 1)
        self.assertTrue(season.is_current)
        self.assertFalse(season.is_started)

    def test_new_season_copies_previous_settings(self):
        with mock.patch("league.models.timezone.localdate", return_value=date(2026, 5, 1)):
            old = Season.current()
        old.name, old.best_of, old.games_per_set = "Sommerliga", 5, 4
        old.started_at = timezone.now()
        old.save()
        with mock.patch("league.models.timezone.localdate", return_value=date(2027, 1, 1)):
            new = Season.current()
            self.assertTrue(new.is_current)
            self.assertFalse(old.is_current)
        self.assertEqual((new.year, new.name, new.best_of, new.games_per_set), (2027, "Sommerliga", 5, 4))
        self.assertIsNone(new.started_at)

    def test_rules(self):
        season = Season(year=2026, best_of=5, games_per_set=4, deciding_match_tiebreak=False,
                        match_tiebreak_points=7)
        self.assertEqual(season.rules, ScoringRules(5, 4, False, 7))
        self.assertEqual(str(season), "Klubliga 2026")


class TournamentTests(TestCase):
    def test_for_players(self):
        m1, m2 = make_user(sex="M"), make_user(sex="M")
        f1, f2 = make_user(sex="F"), make_user(sex="F")
        self.assertEqual(Tournament.for_players(m1), Tournament.MEN_SINGLES)
        self.assertEqual(Tournament.for_players(f1), Tournament.WOMEN_SINGLES)
        self.assertEqual(Tournament.for_players(m1, m2), Tournament.MEN_DOUBLES)
        self.assertEqual(Tournament.for_players(f1, f2), Tournament.WOMEN_DOUBLES)
        self.assertEqual(Tournament.for_players(f1, m1), Tournament.MIXED_DOUBLES)
        self.assertTrue(Tournament.is_doubles("XD"))
        self.assertFalse(Tournament.is_doubles("MS"))


class EntryTests(TestCase):
    def test_names_and_players(self):
        season = make_season()
        anna = make_user("Anna", "Meier", "F")
        ben = make_user("Ben", "Huber", "M")
        single = services.create_entry(season, anna)
        double = services.create_entry(season, anna, ben)
        self.assertEqual(single.name, "Anna Meier")
        self.assertEqual(str(double), "A. Meier / B. Huber")
        self.assertEqual(double.players, [anna, ben])
        self.assertTrue(double.has_player(ben))
        self.assertFalse(single.has_player(ben))

    def test_status(self):
        season = make_season()
        entry = singles(season, 1)[0]
        self.assertEqual(entry.status, Entry.Status.REGISTERED)
        season.started_at = timezone.now()
        season.save()
        entry.refresh_from_db()
        self.assertEqual(entry.status, Entry.Status.WAITING)
        self.assertEqual(entry.status_label, "Waiting for admission")
        place(season, [entry], "B")
        self.assertEqual(entry.status, Entry.Status.PLACED)
        self.assertEqual(entry.status_label, "Group B")
        entry.withdrawn_at = timezone.now()
        self.assertEqual(entry.status, Entry.Status.WITHDRAWN)
        self.assertFalse(entry.is_active)

    def test_queryset_helpers(self):
        season = make_season()
        a, b = singles(season, 2)
        self.assertEqual(list(Entry.objects.of_player(a.player1)), [a])
        services.withdraw_entry(b)
        self.assertEqual(list(Entry.objects.active()), [a])


class MatchTests(TestCase):
    def setUp(self):
        self.season = make_season(started=True)
        self.a, self.b, self.c = singles(self.season, 3)
        place(self.season, [self.a, self.b, self.c], "A")
        self.match = group_match(self.a, self.b)

    def test_states(self):
        m = self.match
        self.assertFalse(m.is_resolved)
        self.assertFalse(m.is_decided)
        self.assertFalse(m.is_knockout)
        self.assertTrue(m.counts)
        self.assertEqual(m.stage_label, "Group A")
        win(m, self.a)
        m.refresh_from_db()
        self.assertTrue(m.is_resolved and m.is_decided)
        self.assertTrue(m.has_player(self.a.player1))
        self.assertFalse(m.has_player(self.c.player1))

    def test_score_perspective(self):
        services.record_result(self.match, [(6, 4), (3, 6), (10, 7)], self.a.player1)
        self.match.refresh_from_db()
        self.assertEqual(self.match.sets(), [(6, 4), (3, 6), (10, 7)])
        self.assertEqual(self.match.score_for(self.match.entry1), "6:4 3:6 10:7")
        self.assertEqual(self.match.score_for(self.match.entry2), "4:6 6:3 7:10")
        self.assertEqual(str(self.match), f"{self.match.entry1} vs {self.match.entry2}")

    def test_counts_only_while_both_entries_are_in_the_group(self):
        place(self.season, [self.b], "B")
        self.assertFalse(Match.objects.filter(pk=self.match.pk).exists())  # open match removed
        match = group_match(self.a, self.c)
        win(match, self.a)
        services.withdraw_entry(self.c)
        match.refresh_from_db()
        self.assertFalse(match.counts)

    def test_knockout_labels(self):
        self.assertEqual(Match(stage=Match.Stage.SEMI, slot=2).stage_label, "Semi-final 2")
        self.assertEqual(Match(stage=Match.Stage.FINAL, slot=1).stage_label, "Final")
        self.assertTrue(Match(stage=Match.Stage.FINAL).counts)
