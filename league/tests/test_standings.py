from types import SimpleNamespace as NS

from django.test import SimpleTestCase

from league.scoring import ScoringRules
from league.standings import compute_standings

RULES = ScoringRules()


def entries(*names):
    return [NS(pk=i, name=name) for i, name in enumerate(names, 1)]


def match(e1, e2, score="", winner=None, status="played"):
    return NS(entry1_id=e1.pk, entry2_id=e2.pk, winner_id=winner.pk if winner else None,
              status=status, score=score)


class StandingsTests(SimpleTestCase):
    def test_ranked_by_wins(self):
        a, b, c = entries("Alpha", "Bravo", "Charlie")
        rows = compute_standings([a, b, c], [
            match(a, b, "4:6 4:6", b), match(b, c, "6:0 6:0", b), match(a, c, "6:0 6:0", a),
        ], RULES)
        self.assertEqual([r.entry for r in rows], [b, a, c])
        self.assertEqual([r.rank for r in rows], [1, 2, 3])
        top = rows[0]
        self.assertEqual((top.played, top.won, top.lost), (2, 2, 0))
        self.assertEqual((top.sets_for, top.sets_against, top.games_for, top.games_against), (4, 0, 24, 8))
        self.assertEqual((top.set_diff, top.game_diff), (4, 16))

    def test_set_and_game_difference(self):
        a, b, c, d = entries("A", "B", "C", "D")
        rows = compute_standings([a, b, c, d], [
            match(a, c, "6:0 6:0", a),
            match(b, d, "6:0 3:6 10:8", b),
            match(c, d, "6:4 6:4", c),
        ], RULES)
        self.assertEqual([r.entry for r in rows][:2], [a, b])  # equal wins, a better set diff

        rows = compute_standings([a, b, c, d], [
            match(a, c, "6:4 6:4", a), match(b, d, "6:1 6:1", b),
        ], RULES)
        self.assertEqual([r.entry for r in rows][:2], [b, a])  # games decide

    def test_head_to_head(self):
        a, b, c, d = entries("Alpha", "Bravo", "Charlie", "Delta")
        # Alpha and Bravo: one win each, identical sets and games; Bravo won the direct match.
        rows = compute_standings([a, b, c, d], [
            match(a, b, "4:6 4:6", b),
            match(a, c, "6:4 6:4", a),
            match(b, d, "4:6 4:6", d),
        ], RULES)
        self.assertEqual([r.entry.name for r in rows], ["Delta", "Bravo", "Alpha", "Charlie"])

    def test_three_way_tie_is_alphabetical(self):
        a, b, c = entries("Charlie", "alpha", "Bravo")
        rows = compute_standings([a, b, c], [
            match(a, b, "6:4 6:4", a), match(b, c, "6:4 6:4", b), match(c, a, "6:4 6:4", c),
        ], RULES)
        self.assertEqual([r.entry.name for r in rows], ["alpha", "Bravo", "Charlie"])

    def test_walkover_counts_as_straight_sets(self):
        a, b = entries("A", "B")
        rows = compute_standings([a, b], [match(a, b, winner=b, status="walkover")], RULES)
        self.assertEqual(rows[0].entry, b)
        self.assertEqual((rows[0].sets_for, rows[0].games_for, rows[1].games_against), (2, 12, 12))

    def test_ignores_open_cancelled_and_foreign_matches(self):
        a, b, outsider = entries("A", "B", "Gone")
        rows = compute_standings([a, b], [
            match(a, b, status="pending"),
            match(a, b, status="cancelled"),
            match(a, outsider, "6:0 6:0", a),
        ], RULES)
        self.assertTrue(all(r.played == 0 for r in rows))
        self.assertEqual([r.entry.name for r in rows], ["A", "B"])
