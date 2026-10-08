"""All changes to league state go through this module.

Every function that changes entries, groups or results finishes with
:func:`sync_tournament`, which reconciles the derived data (group matches and
knockout matches) with the current state.
"""

import random
from itertools import combinations

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Entry, Group, Match, Season, Tournament
from .scoring import evaluate, format_score
from .standings import compute_standings

KNOCKOUT_STAGES = (Match.Stage.SEMI, Match.Stage.FINAL)
DECIDED = (Match.Status.PLAYED, Match.Status.WALKOVER)


class LeagueError(Exception):
    """An action is not allowed; the message is shown to the user."""


# Entries ---------------------------------------------------------------------

def create_entry(season, player, partner=None, created_by=None):
    if partner is not None and partner.pk == player.pk:
        raise LeagueError(_("You cannot be your own partner."))
    tournament = Tournament.for_players(player, partner)
    label = Tournament(tournament).label
    for person in (player, partner):
        if person is not None and (
            Entry.objects.active().filter(season=season, tournament=tournament).of_player(person).exists()
        ):
            raise LeagueError(_("%(player)s already has an entry in %(tournament)s.")
                              % {"player": person, "tournament": label})
    return Entry.objects.create(
        season=season, tournament=tournament, player1=player, player2=partner,
        created_by=created_by or player,
    )


def in_knockout(entry):
    return Match.objects.filter(stage__in=KNOCKOUT_STAGES).filter(Q(entry1=entry) | Q(entry2=entry)).exists()


def can_withdraw(entry):
    return entry.is_active and entry.season.is_current and not in_knockout(entry)


@transaction.atomic
def withdraw_entry(entry):
    if not entry.is_active:
        raise LeagueError(_("This entry has already been withdrawn."))
    if in_knockout(entry):
        raise LeagueError(_("The knockout stage has begun – please ask the organiser."))
    entry.withdrawn_at = timezone.now()
    entry.save(update_fields=["withdrawn_at"])
    sync_tournament(entry.season, entry.tournament)


# Groups ------------------------------------------------------------------

def get_group(season, tournament, name):
    group, _ = Group.objects.get_or_create(season=season, tournament=tournament, name=name)
    return group


def has_results(season, tournament):
    return Match.objects.filter(season=season, tournament=tournament).exclude(
        status=Match.Status.PENDING).exists()


def knockout_has_results(season, tournament):
    return Match.objects.filter(
        season=season, tournament=tournament, stage__in=KNOCKOUT_STAGES, status__in=DECIDED
    ).exists()


def suggested_group_count(season, entry_count):
    return 2 if entry_count >= season.two_groups_from else 1


@transaction.atomic
def assign_groups(season, tournament, assignment):
    """Apply ``{entry: group name or None}`` and update the matches."""
    changed = [(e, name) for e, name in assignment.items() if (e.group.name if e.group_id else None) != name]
    if not changed:
        return 0
    if knockout_has_results(season, tournament):
        raise LeagueError(_("The knockout stage already has results – groups can no longer be changed."))
    for entry, name in changed:
        if not entry.is_active or entry.season_id != season.pk or entry.tournament != tournament:
            raise LeagueError(_("%(entry)s cannot be placed in this tournament.") % {"entry": entry})
        entry.group = get_group(season, tournament, name) if name else None
        entry.save(update_fields=["group"])
    sync_tournament(season, tournament)
    return len(changed)


@transaction.atomic
def random_split(season, tournament, group_count, rng=random):
    if group_count not in (1, 2):
        raise LeagueError(_("A tournament has one or two groups."))
    if has_results(season, tournament):
        raise LeagueError(_("Results have already been entered – random split is no longer possible."))
    entries = list(Entry.objects.active().filter(season=season, tournament=tournament))
    rng.shuffle(entries)
    groups = [get_group(season, tournament, name) for name in "AB"[:group_count]]
    for index, entry in enumerate(entries):
        entry.group = groups[index % group_count]
        entry.save(update_fields=["group"])
    sync_tournament(season, tournament)


def sync_group(group):
    """Make the group's matches match its composition (one match per pair)."""
    ids = sorted(group.active_entries().values_list("pk", flat=True))
    wanted = set(combinations(ids, 2))
    existing = {(m.entry1_id, m.entry2_id): m for m in group.matches.filter(stage=Match.Stage.GROUP)}
    for pair, match in existing.items():
        if pair not in wanted and match.status == Match.Status.PENDING:
            match.delete()
    Match.objects.bulk_create([
        Match(season_id=group.season_id, tournament=group.tournament, stage=Match.Stage.GROUP,
              group=group, entry1_id=a, entry2_id=b)
        for a, b in sorted(wanted - existing.keys())
    ])


def counting_matches(group, entries=None):
    entries = list(group.active_entries()) if entries is None else entries
    ids = {e.pk for e in entries}
    return [
        m for m in group.matches.filter(stage=Match.Stage.GROUP)
        if m.entry1_id in ids and m.entry2_id in ids
    ]


def group_standings(group, entries=None, matches=None):
    entries = list(group.active_entries()) if entries is None else entries
    matches = counting_matches(group, entries) if matches is None else matches
    return compute_standings(entries, matches, group.season.rules)


def group_is_complete(group, entries=None, matches=None):
    entries = list(group.active_entries()) if entries is None else entries
    if len(entries) < 2:
        return False
    matches = counting_matches(group, entries) if matches is None else matches
    return all(m.is_resolved for m in matches)


def active_groups(season, tournament):
    groups = Group.objects.filter(season=season, tournament=tournament).order_by("name")
    return [g for g in groups if g.active_entries().exists()]


# Knockout --------------------------------------------------------------------

def knockout_layout(group_count):
    """Slots of the knockout stage with placeholder labels for both sides."""
    if group_count == 1:
        return [(Match.Stage.FINAL, 1, _("Final"), _("Winner"), _("Runner-up"))]
    if group_count == 2:
        return [
            (Match.Stage.SEMI, 1, _("Semi-final 1"), _("Winner Group A"), _("Runner-up Group B")),
            (Match.Stage.SEMI, 2, _("Semi-final 2"), _("Winner Group B"), _("Runner-up Group A")),
            (Match.Stage.FINAL, 1, _("Final"), _("Winner semi-final 1"), _("Winner semi-final 2")),
        ]
    return []


def _top_two(group):
    rows = group_standings(group)
    return rows[0].entry, rows[1].entry


def sync_knockout(season, tournament):
    groups = active_groups(season, tournament)
    ready = groups and all(group_is_complete(g) for g in groups)
    existing = {
        (m.stage, m.slot): m
        for m in Match.objects.filter(season=season, tournament=tournament, stage__in=KNOCKOUT_STAGES)
    }

    def apply(stage, slot, pairing):
        match = existing.get((stage, slot))
        if pairing is None:
            if match is not None and match.status == Match.Status.PENDING:
                match.delete()
                del existing[(stage, slot)]
            return
        e1, e2 = pairing
        if match is None:
            existing[(stage, slot)] = Match.objects.create(
                season=season, tournament=tournament, stage=stage, slot=slot, entry1=e1, entry2=e2)
        elif match.status == Match.Status.PENDING and (match.entry1_id, match.entry2_id) != (e1.pk, e2.pk):
            match.entry1, match.entry2 = e1, e2
            match.save(update_fields=["entry1", "entry2"])

    semis = [None, None]
    final = None
    if ready and len(groups) == 1:
        final = _top_two(groups[0])
    elif ready and len(groups) == 2:
        a1, a2 = _top_two(groups[0])
        b1, b2 = _top_two(groups[1])
        semis = [(a1, b2), (b1, a2)]
    apply(Match.Stage.SEMI, 1, semis[0])
    apply(Match.Stage.SEMI, 2, semis[1])
    if len(groups) == 2:
        s1, s2 = existing.get((Match.Stage.SEMI, 1)), existing.get((Match.Stage.SEMI, 2))
        if s1 and s2 and s1.is_decided and s2.is_decided:
            final = (s1.winner, s2.winner)
    apply(Match.Stage.FINAL, 1, final)


@transaction.atomic
def sync_tournament(season, tournament):
    for group in Group.objects.filter(season=season, tournament=tournament):
        sync_group(group)
    sync_knockout(season, tournament)


# Results ---------------------------------------------------------------------

def is_locked(match):
    """Players can no longer change a result once the following stage has a result."""
    later = {Match.Stage.GROUP: KNOCKOUT_STAGES, Match.Stage.SEMI: (Match.Stage.FINAL,)}.get(match.stage)
    if not later:
        return False
    return Match.objects.filter(
        season_id=match.season_id, tournament=match.tournament, stage__in=later, status__in=DECIDED
    ).exists()


def can_edit_result(match, user):
    if user.is_staff:
        return True
    return (
        match.has_player(user)
        and match.season.is_current
        and match.season.is_started
        and match.status in (Match.Status.PENDING, Match.Status.PLAYED)
        and match.counts
        and not is_locked(match)
    )


def _save_outcome(match, status, user, score="", winner=None):
    match.status = status
    match.score = score
    match.winner = winner
    match.reported_by = user
    match.reported_at = timezone.now() if status != Match.Status.PENDING else None
    match.save()
    sync_tournament(match.season, match.tournament)


@transaction.atomic
def record_result(match, sets, user):
    """Store a played result; ``sets`` are seen from entry1. Raises ScoreError."""
    outcome = evaluate(sets, match.season.rules)
    winner = match.entry1 if outcome.winner == 1 else match.entry2
    _save_outcome(match, Match.Status.PLAYED, user, format_score(sets), winner)


@transaction.atomic
def record_walkover(match, winner, user):
    if winner.pk not in (match.entry1_id, match.entry2_id):
        raise LeagueError(_("The winner must be one of the two entries."))
    _save_outcome(match, Match.Status.WALKOVER, user, winner=winner)


@transaction.atomic
def cancel_match(match, user):
    if match.is_knockout:
        raise LeagueError(_("Knockout matches cannot be cancelled – record a walkover instead."))
    _save_outcome(match, Match.Status.CANCELLED, user)


@transaction.atomic
def reset_match(match, user):
    _save_outcome(match, Match.Status.PENDING, None)


# Season ------------------------------------------------------------------

def start_season(season):
    if season.is_started:
        raise LeagueError(_("The league has already started."))
    season.started_at = timezone.now()
    season.save(update_fields=["started_at"])


@transaction.atomic
def close_groups(groups, user):
    """Mark all open matches of the given groups as not played. Returns the count."""
    groups = list(groups)
    count = 0
    for group in groups:
        sync_group(group)
        count += group.matches.filter(stage=Match.Stage.GROUP, status=Match.Status.PENDING).update(
            status=Match.Status.CANCELLED, reported_by=user, reported_at=timezone.now())
    for season_id, tournament in {(g.season_id, g.tournament) for g in groups}:
        sync_knockout(Season.objects.get(pk=season_id), tournament)
    return count


def close_tournament(season, tournament, user):
    return close_groups(Group.objects.filter(season=season, tournament=tournament), user)


def close_all(season, user):
    return close_groups(Group.objects.filter(season=season), user)
