import random

from django.test import TestCase

from league import services
from league.models import Entry, Match, Tournament
from league.scoring import ScoreError
from league.services import LeagueError

from .helpers import group_match, make_season, make_user, place, play_round_robin, singles, win


def ko(season, tournament="MS"):
    return {
        (m.stage, m.slot): m
        for m in Match.objects.filter(season=season, tournament=tournament).exclude(stage="group")
    }


class EntryServiceTests(TestCase):
    def setUp(self):
        self.season = make_season()
        self.max = make_user("Max", sex="M")
        self.eva = make_user("Eva", sex="F")

    def test_create_singles_and_doubles(self):
        single = services.create_entry(self.season, self.max)
        mixed = services.create_entry(self.season, self.max, self.eva)
        self.assertEqual(single.tournament, Tournament.MEN_SINGLES)
        self.assertEqual(mixed.tournament, Tournament.MIXED_DOUBLES)
        self.assertEqual(mixed.created_by, self.max)

    def test_one_active_entry_per_tournament(self):
        services.create_entry(self.season, self.max, self.eva)
        with self.assertRaisesMessage(LeagueError, "ist bereits für Mixed gemeldet"):
            services.create_entry(self.season, self.max, make_user(sex="F"))
        with self.assertRaisesMessage(LeagueError, str(self.eva)):
            services.create_entry(self.season, make_user(sex="M"), self.eva)

    def test_reenter_after_withdrawal(self):
        entry = services.create_entry(self.season, self.max)
        services.withdraw_entry(entry)
        services.create_entry(self.season, self.max)
        self.assertEqual(Entry.objects.filter(player1=self.max).count(), 2)

    def test_not_own_partner(self):
        with self.assertRaises(LeagueError):
            services.create_entry(self.season, self.max, self.max)

    def test_withdraw_twice(self):
        entry = services.create_entry(self.season, self.max)
        services.withdraw_entry(entry)
        self.assertFalse(services.can_withdraw(entry))
        with self.assertRaises(LeagueError):
            services.withdraw_entry(entry)


class GroupServiceTests(TestCase):
    def setUp(self):
        self.season = make_season(started=True)
        self.entries = singles(self.season, 4)

    def test_round_robin_matches(self):
        place(self.season, self.entries, "A")
        self.assertEqual(Match.objects.filter(stage="group").count(), 6)
        for match in Match.objects.all():
            self.assertLess(match.entry1_id, match.entry2_id)
        # Saving the same assignment again changes nothing.
        self.assertEqual(services.assign_groups(self.season, "MS", {e: "A" for e in self.entries}), 0)

    def test_add_late_entry(self):
        place(self.season, self.entries, "A")
        late = singles(self.season, 1, prefix="Late")[0]
        self.assertEqual(late.status, Entry.Status.WAITING)
        place(self.season, [late], "A")
        self.assertEqual(Match.objects.filter(stage="group").count(), 10)

    def test_move_keeps_played_and_revives(self):
        a, b, c, d = self.entries
        place(self.season, self.entries, "A")
        played = group_match(a, b)
        win(played, a)
        place(self.season, [b], "B")
        self.assertEqual(Match.objects.filter(group__name="A").count(), 4)  # 3 open + played kept
        played.refresh_from_db()
        self.assertFalse(played.counts)
        self.assertEqual(Match.objects.filter(group__name="B").count(), 0)  # alone in B
        place(self.season, [b], "A")
        self.assertEqual(Match.objects.filter(group__name="A").count(), 6)
        played.refresh_from_db()
        self.assertTrue(played.counts and played.is_decided)

    def test_withdrawal_removes_open_matches_and_standings(self):
        a, b, c, d = self.entries
        place(self.season, self.entries, "A")
        win(group_match(a, d), d)
        services.withdraw_entry(d)
        self.assertEqual(Match.objects.filter(stage="group").count(), 4)  # 3 among a,b,c + played
        rows = services.group_standings(a.group)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r.played == 0 for r in rows))

    def test_random_split(self):
        entries = self.entries + singles(self.season, 1, prefix="Q")
        services.random_split(self.season, "MS", 2, random.Random(3))
        sizes = sorted(Entry.objects.filter(group__name=n).count() for n in "AB")
        self.assertEqual(sizes, [2, 3])
        self.assertEqual(Match.objects.count(), 1 + 3)
        services.random_split(self.season, "MS", 1, random.Random(3))
        self.assertEqual(Entry.objects.filter(group__name="A").count(), len(entries))
        self.assertEqual(Match.objects.count(), 10)
        with self.assertRaises(LeagueError):
            services.random_split(self.season, "MS", 3)
        win(Match.objects.first(), Match.objects.first().entry1)
        with self.assertRaisesMessage(LeagueError, "Es wurden schon Ergebnisse eingetragen"):
            services.random_split(self.season, "MS", 2)

    def test_suggested_group_count(self):
        self.assertEqual(services.suggested_group_count(self.season, 7), 1)
        self.assertEqual(services.suggested_group_count(self.season, 8), 2)

    def test_assign_rejects_foreign_entry(self):
        woman = singles(self.season, 1, sex="F")[0]
        with self.assertRaises(LeagueError):
            services.assign_groups(self.season, "MS", {woman: "A"})

    def test_group_complete(self):
        a, b, c, d = self.entries
        place(self.season, [a], "A")
        self.assertFalse(services.group_is_complete(a.group))  # a single entry
        place(self.season, [b, c], "A")
        self.assertFalse(services.group_is_complete(a.group))
        play_round_robin([a, b, c])
        self.assertTrue(services.group_is_complete(a.group))
        self.assertEqual([r.entry for r in services.group_standings(a.group)], [a, b, c])


class ResultServiceTests(TestCase):
    def setUp(self):
        self.season = make_season(started=True)
        self.a, self.b, self.c = singles(self.season, 3)
        place(self.season, [self.a, self.b, self.c], "A")
        self.match = group_match(self.a, self.b)

    def test_record_result(self):
        services.record_result(self.match, [(4, 6), (6, 3), (5, 10)], self.a.player1)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.PLAYED)
        self.assertEqual(self.match.score, "4:6 6:3 5:10")
        self.assertEqual(self.match.winner, self.match.entry2)
        self.assertEqual(self.match.reported_by, self.a.player1)
        self.assertIsNotNone(self.match.reported_at)

    def test_invalid_result_is_not_saved(self):
        with self.assertRaises(ScoreError):
            services.record_result(self.match, [(6, 4)], self.a.player1)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.PENDING)

    def test_walkover_cancel_reset(self):
        services.record_walkover(self.match, self.b, None)
        self.match.refresh_from_db()
        self.assertEqual((self.match.status, self.match.winner), (Match.Status.WALKOVER, self.b))
        with self.assertRaises(LeagueError):
            services.record_walkover(self.match, self.c, None)
        services.cancel_match(self.match, None)
        self.match.refresh_from_db()
        self.assertEqual((self.match.status, self.match.winner), (Match.Status.CANCELLED, None))
        services.reset_match(self.match, None)
        self.match.refresh_from_db()
        self.assertEqual((self.match.status, self.match.reported_at), (Match.Status.PENDING, None))

    def test_can_edit_result(self):
        player = self.a.player1
        self.assertTrue(services.can_edit_result(self.match, player))
        self.assertFalse(services.can_edit_result(self.match, self.c.player1))
        self.assertTrue(services.can_edit_result(self.match, make_user(is_staff=True)))
        self.season.started_at = None
        self.season.save()
        self.match.refresh_from_db()
        self.assertFalse(services.can_edit_result(self.match, player))

    def test_cannot_edit_walkover_set_by_admin(self):
        services.record_walkover(self.match, self.b, None)
        self.match.refresh_from_db()
        self.assertFalse(services.can_edit_result(self.match, self.a.player1))

    def test_start_season(self):
        with self.assertRaises(LeagueError):
            services.start_season(self.season)
        season = make_season()
        season.started_at = None
        services.start_season(season)
        self.assertTrue(season.is_started)


class KnockoutTests(TestCase):
    def setUp(self):
        self.season = make_season(started=True)

    def test_single_group_final(self):
        a, b, c = singles(self.season, 3)
        place(self.season, [a, b, c], "A")
        self.assertEqual(services.knockout_layout(1)[0][2], "Finale")
        play_round_robin([c, a, b])
        final = ko(self.season)[("final", 1)]
        self.assertEqual((final.entry1, final.entry2), (c, a))
        self.assertTrue(services.is_locked(group_match(a, b)) is False)
        win(final, a)
        self.assertTrue(services.is_locked(group_match(a, b)))
        self.assertFalse(services.can_edit_result(group_match(a, b), a.player1))
        self.assertFalse(services.is_locked(Match.objects.get(stage="final")))

    def test_reopening_group_removes_open_final(self):
        a, b = singles(self.season, 2)
        place(self.season, [a, b], "A")
        match = group_match(a, b)
        win(match, b)
        self.assertIn(("final", 1), ko(self.season))
        services.reset_match(match, None)
        self.assertEqual(ko(self.season), {})

    def test_two_groups_semis_and_final(self):
        a = singles(self.season, 3, prefix="A")
        b = singles(self.season, 3, prefix="B")
        place(self.season, a, "A")
        place(self.season, b, "B")
        self.assertEqual(len(services.knockout_layout(2)), 3)
        play_round_robin(a)
        self.assertEqual(ko(self.season), {})  # group B not finished yet
        play_round_robin(b)
        matches = ko(self.season)
        semi1, semi2 = matches[("semi", 1)], matches[("semi", 2)]
        self.assertEqual((semi1.entry1, semi1.entry2), (a[0], b[1]))
        self.assertEqual((semi2.entry1, semi2.entry2), (b[0], a[1]))
        self.assertNotIn(("final", 1), matches)

        # A changed group result re-seeds the open semi-finals.
        services.reset_match(group_match(a[0], a[1]), None)
        self.assertEqual(ko(self.season), {})  # group A open again: semis withdrawn
        win(group_match(a[0], a[1]), a[1])
        semi1 = ko(self.season)[("semi", 1)]
        self.assertEqual(semi1.entry1, a[1])

        win(semi1, semi1.entry2)
        self.assertNotIn(("final", 1), ko(self.season))
        semi2 = ko(self.season)[("semi", 2)]
        win(semi2, semi2.entry1)
        final = ko(self.season)[("final", 1)]
        self.assertEqual((final.entry1, final.entry2), (b[1], b[0]))

        # Withdrawal and group changes are locked now.
        self.assertFalse(services.can_withdraw(b[0]))
        with self.assertRaises(LeagueError):
            services.withdraw_entry(b[0])
        with self.assertRaises(LeagueError):
            services.assign_groups(self.season, "MS", {a[2]: "B"})
        with self.assertRaises(LeagueError):
            services.cancel_match(final, None)
        self.assertFalse(services.is_locked(semi1))
        win(final, final.entry1)
        self.assertTrue(services.is_locked(semi1))

    def test_close_group_phase(self):
        a = singles(self.season, 3, prefix="A")
        b = singles(self.season, 2, prefix="B")
        place(self.season, a, "A")
        place(self.season, b, "B")
        win(group_match(a[0], a[1]), a[0])
        group_a = a[0].group
        self.assertEqual(services.close_groups([group_a], None), 2)
        self.assertTrue(services.group_is_complete(group_a))
        self.assertEqual(ko(self.season), {})
        self.assertEqual(services.close_tournament(self.season, "MS", None), 1)
        self.assertEqual(len(ko(self.season)), 2)
        self.assertEqual(services.close_all(self.season, None), 0)

    def test_close_all_covers_every_tournament(self):
        men = singles(self.season, 2, prefix="M")
        women = singles(self.season, 2, sex="F", prefix="W")
        place(self.season, men, "A")
        place(self.season, women, "A")
        self.assertEqual(services.close_all(self.season, None), 2)
        self.assertIn(("final", 1), ko(self.season, "MS"))
        self.assertIn(("final", 1), ko(self.season, "WS"))
