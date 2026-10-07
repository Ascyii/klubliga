from django.test import SimpleTestCase

from league.scoring import (
    ScoreError, ScoringRules, evaluate, flip, format_score, parse_score, summarize,
    validate_set, walkover_outcome,
)

DEFAULT = ScoringRules()


class ParseFormatTests(SimpleTestCase):
    def test_parse_colon_and_dash(self):
        self.assertEqual(parse_score("6:4 3:6 10:8"), [(6, 4), (3, 6), (10, 8)])
        self.assertEqual(parse_score(" 6-4, 3 - 6 ;7/5 "), [(6, 4), (3, 6), (7, 5)])

    def test_parse_empty(self):
        self.assertEqual(parse_score("   "), [])

    def test_parse_invalid(self):
        with self.assertRaises(ScoreError):
            parse_score("6:4 x")
        with self.assertRaises(ScoreError):
            parse_score("6:4:2")

    def test_format_and_flip(self):
        self.assertEqual(format_score([(6, 4), (10, 8)]), "6:4 10:8")
        self.assertEqual(flip([(6, 4), (3, 6)]), [(4, 6), (6, 3)])


class RulesTests(SimpleTestCase):
    def test_sets_to_win(self):
        self.assertEqual(ScoringRules(best_of=1).sets_to_win, 1)
        self.assertEqual(ScoringRules(best_of=3).sets_to_win, 2)
        self.assertEqual(ScoringRules(best_of=5).sets_to_win, 3)

    def test_tiebreak_set(self):
        self.assertTrue(DEFAULT.is_tiebreak_set(2))
        self.assertFalse(DEFAULT.is_tiebreak_set(1))
        self.assertFalse(ScoringRules(deciding_match_tiebreak=False).is_tiebreak_set(2))
        self.assertFalse(ScoringRules(best_of=1).is_tiebreak_set(0))
        self.assertTrue(ScoringRules(best_of=5).is_tiebreak_set(4))


class ValidateSetTests(SimpleTestCase):
    def test_valid_sets(self):
        for a, b in [(6, 0), (6, 4), (7, 5), (7, 6), (4, 6), (6, 7)]:
            with self.subTest(score=(a, b)):
                self.assertEqual(validate_set(a, b, DEFAULT), 1 if a > b else 2)

    def test_invalid_sets(self):
        for a, b in [(6, 5), (8, 6), (7, 3), (5, 3), (6, 6), (0, 0), (10, 8)]:
            with self.subTest(score=(a, b)), self.assertRaises(ScoreError):
                validate_set(a, b, DEFAULT)

    def test_match_tiebreak(self):
        for a, b in [(10, 8), (12, 10), (10, 0), (8, 10)]:
            with self.subTest(score=(a, b)):
                validate_set(a, b, DEFAULT, tiebreak=True)
        for a, b in [(9, 7), (10, 9), (13, 10), (6, 4), (11, 11)]:
            with self.subTest(score=(a, b)), self.assertRaises(ScoreError):
                validate_set(a, b, DEFAULT, tiebreak=True)

    def test_short_sets(self):
        rules = ScoringRules(games_per_set=4)
        validate_set(4, 2, rules)
        validate_set(5, 4, rules)
        validate_set(5, 3, rules)
        with self.assertRaises(ScoreError):
            validate_set(4, 3, rules)


class EvaluateTests(SimpleTestCase):
    def test_straight_sets(self):
        outcome = evaluate([(6, 4), (7, 5)], DEFAULT)
        self.assertEqual(outcome.winner, 1)
        self.assertEqual(outcome.sets, (2, 0))
        self.assertEqual(outcome.games, (13, 9))

    def test_three_sets_with_match_tiebreak(self):
        outcome = evaluate([(6, 4), (3, 6), (8, 10)], DEFAULT)
        self.assertEqual(outcome.winner, 2)
        self.assertEqual(outcome.sets, (1, 2))
        self.assertEqual(outcome.games, (9, 11))  # tie-break counts as one game

    def test_third_set_must_be_tiebreak(self):
        with self.assertRaisesMessage(ScoreError, "Set 3"):
            evaluate([(6, 4), (3, 6), (6, 4)], DEFAULT)

    def test_full_third_set(self):
        rules = ScoringRules(deciding_match_tiebreak=False)
        self.assertEqual(evaluate([(6, 4), (3, 6), (7, 5)], rules).winner, 1)
        with self.assertRaises(ScoreError):
            evaluate([(6, 4), (3, 6), (10, 8)], rules)

    def test_too_many_sets(self):
        with self.assertRaisesMessage(ScoreError, "already decided"):
            evaluate([(6, 4), (6, 4), (10, 8)], DEFAULT)

    def test_not_finished(self):
        with self.assertRaisesMessage(ScoreError, "not finished"):
            evaluate([(6, 4)], DEFAULT)
        with self.assertRaisesMessage(ScoreError, "not finished"):
            evaluate([(6, 4), (4, 6)], DEFAULT)

    def test_empty(self):
        with self.assertRaises(ScoreError):
            evaluate([], DEFAULT)

    def test_best_of_one_and_five(self):
        self.assertEqual(evaluate([(4, 6)], ScoringRules(best_of=1)).winner, 2)
        rules = ScoringRules(best_of=5)
        outcome = evaluate([(6, 4), (4, 6), (6, 4), (4, 6), (10, 7)], rules)
        self.assertEqual((outcome.winner, outcome.sets), (1, (3, 2)))


class SummarizeWalkoverTests(SimpleTestCase):
    def test_summarize_does_not_validate(self):
        # The drawn set is skipped entirely; the third set is a match tie-break worth one game.
        self.assertEqual(summarize([(6, 4), (5, 5), (2, 6)], DEFAULT), ((1, 1), (6, 5)))

    def test_walkover(self):
        self.assertEqual(walkover_outcome(1, DEFAULT).games, (12, 0))
        outcome = walkover_outcome(2, ScoringRules(best_of=5, games_per_set=4))
        self.assertEqual((outcome.winner, outcome.sets, outcome.games), (2, (0, 3), (0, 12)))
