"""Group standings. Works on plain objects so it can be tested without a database.

``entries`` need ``pk`` and ``name``; ``matches`` need ``entry1_id``,
``entry2_id``, ``winner_id``, ``status`` and ``score``.
"""

from dataclasses import dataclass, field
from itertools import groupby

from .scoring import parse_score, summarize, walkover_outcome

PLAYED, WALKOVER = "played", "walkover"


@dataclass
class Row:
    entry: object
    played: int = 0
    won: int = 0
    lost: int = 0
    sets_for: int = 0
    sets_against: int = 0
    games_for: int = 0
    games_against: int = 0
    rank: int = 0
    is_mine: bool = field(default=False, compare=False)

    @property
    def set_diff(self):
        return self.sets_for - self.sets_against

    @property
    def game_diff(self):
        return self.games_for - self.games_against

    def sort_key(self):
        return (-self.won, -self.set_diff, -self.game_diff)


def match_totals(match, rules):
    """Return ``(sets, games)`` tuples from entry1's perspective, or None."""
    if match.status == WALKOVER:
        outcome = walkover_outcome(1 if match.winner_id == match.entry1_id else 2, rules)
        return outcome.sets, outcome.games
    if match.status == PLAYED:
        return summarize(parse_score(match.score), rules)
    return None


def compute_standings(entries, matches, rules):
    rows = {entry.pk: Row(entry) for entry in entries}
    decided = []
    for match in matches:
        if match.status not in (PLAYED, WALKOVER):
            continue
        if match.entry1_id not in rows or match.entry2_id not in rows:
            continue  # does not count (withdrawn or moved entry)
        totals = match_totals(match, rules)
        if totals is None:
            continue
        decided.append(match)
        (sets1, sets2), (games1, games2) = totals
        for row, sets_for, sets_against, games_for, games_against in (
            (rows[match.entry1_id], sets1, sets2, games1, games2),
            (rows[match.entry2_id], sets2, sets1, games2, games1),
        ):
            row.played += 1
            row.sets_for += sets_for
            row.sets_against += sets_against
            row.games_for += games_for
            row.games_against += games_against
            if match.winner_id == row.entry.pk:
                row.won += 1
            else:
                row.lost += 1

    ordered = sorted(rows.values(), key=lambda r: (r.sort_key(), r.entry.name.lower()))
    result = []
    for _, tied in groupby(ordered, key=Row.sort_key):
        tied = list(tied)
        if len(tied) == 2:
            tied = _head_to_head(tied, decided)
        result.extend(tied)
    for rank, row in enumerate(result, start=1):
        row.rank = rank
    return result


def _head_to_head(pair, matches):
    a, b = pair
    ids = {a.entry.pk, b.entry.pk}
    for match in matches:
        if {match.entry1_id, match.entry2_id} == ids:
            return [a, b] if match.winner_id == a.entry.pk else [b, a]
    return pair
