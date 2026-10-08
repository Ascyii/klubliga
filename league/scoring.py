"""Tennis score validation and evaluation. Pure functions, no database access.

A score is a list of sets, each a tuple ``(games side 1, games side 2)``.
For a match tie-break the tuple holds points instead of games.
"""

import re
from dataclasses import dataclass

from django.utils.translation import gettext as _


class ScoreError(ValueError):
    """The score is not valid under the given rules."""


@dataclass(frozen=True)
class ScoringRules:
    best_of: int = 3
    games_per_set: int = 6
    deciding_match_tiebreak: bool = True
    match_tiebreak_points: int = 10

    @property
    def sets_to_win(self):
        return self.best_of // 2 + 1

    def is_tiebreak_set(self, index):
        """True if the set at ``index`` (0-based) is played as a match tie-break."""
        return self.deciding_match_tiebreak and self.best_of > 1 and index == self.best_of - 1


@dataclass(frozen=True)
class Outcome:
    winner: int  # 1 or 2
    sets: tuple  # (sets won by side 1, sets won by side 2)
    games: tuple  # (games won by side 1, games won by side 2)


_SET_RE = re.compile(r"^(\d{1,2}):(\d{1,2})$")


def parse_score(text):
    """Parse ``"6:4 3:6 10:8"`` (also ``6-4, 3-6``) into a list of tuples."""
    normalized = re.sub(r"\s*[:\-/]\s*", ":", text.strip())
    sets = []
    for token in re.split(r"[\s,;]+", normalized):
        if not token:
            continue
        match = _SET_RE.match(token)
        if not match:
            raise ScoreError(_("Cannot read the set score “%(set)s”.") % {"set": token})
        sets.append((int(match.group(1)), int(match.group(2))))
    return sets


def format_score(sets):
    return " ".join(f"{a}:{b}" for a, b in sets)


def flip(sets):
    return [(b, a) for a, b in sets]


def validate_set(a, b, rules, tiebreak=False):
    """Validate one set and return the winning side (1 or 2)."""
    if a == b:
        raise ScoreError(_("A set cannot end in a draw."))
    high, low = max(a, b), min(a, b)
    if tiebreak:
        points = rules.match_tiebreak_points
        if high < points:
            raise ScoreError(_("A match tie-break is won with at least %(points)s points.") % {"points": points})
        if high - low < 2:
            raise ScoreError(_("A match tie-break must be won by two points."))
        if high > points and high - low != 2:
            raise ScoreError(
                _("Beyond %(points)s points a match tie-break ends with a two-point lead.") % {"points": points})
    else:
        games = rules.games_per_set
        valid = (high == games and low <= games - 2) or (high == games + 1 and low in (games - 1, games))
        if not valid:
            raise ScoreError(_("%(a)s:%(b)s is not a valid set score.") % {"a": a, "b": b})
    return 1 if a > b else 2


def summarize(sets, rules):
    """Count sets and games without validating. A match tie-break counts as
    one set and as one game for its winner."""
    sets_won, games_won = [0, 0], [0, 0]
    for index, (a, b) in enumerate(sets):
        if a == b:
            continue
        side = 0 if a > b else 1
        sets_won[side] += 1
        if rules.is_tiebreak_set(index):
            games_won[side] += 1
        else:
            games_won[0] += a
            games_won[1] += b
    return tuple(sets_won), tuple(games_won)


def evaluate(sets, rules):
    """Validate a complete match score and return its :class:`Outcome`."""
    if not sets:
        raise ScoreError(_("Please enter the score."))
    won = [0, 0]
    for index, (a, b) in enumerate(sets):
        if max(won) == rules.sets_to_win:
            raise ScoreError(_("Too many sets: the match was already decided."))
        try:
            side = validate_set(a, b, rules, tiebreak=rules.is_tiebreak_set(index))
        except ScoreError as error:
            raise ScoreError(_("Set %(number)s: %(error)s") % {"number": index + 1, "error": error}) from None
        won[side - 1] += 1
    if max(won) < rules.sets_to_win:
        raise ScoreError(_("The match is not finished: %(sets)s sets are needed to win.")
                         % {"sets": rules.sets_to_win})
    sets_won, games_won = summarize(sets, rules)
    return Outcome(winner=1 if won[0] > won[1] else 2, sets=sets_won, games=games_won)


def walkover_outcome(winner, rules):
    """A walkover counts as a straight-sets win with every set won to zero."""
    sets = (rules.sets_to_win, 0)
    games = (rules.sets_to_win * rules.games_per_set, 0)
    if winner == 2:
        sets, games = sets[::-1], games[::-1]
    return Outcome(winner=winner, sets=sets, games=games)
