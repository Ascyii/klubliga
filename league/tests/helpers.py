from django.utils import timezone

from accounts.models import User
from league import services
from league.models import Match, Season

_counter = 0


def make_user(first="Player", last=None, sex="M", confirmed=True, **extra):
    global _counter
    _counter += 1
    user = User.objects.create_user(
        email=f"user{_counter}@example.com", first_name=first,
        last_name=last or f"Last{_counter:03d}", sex=sex, **extra,
    )
    if confirmed:
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
    return user


def make_season(started=False, **settings):
    season = Season.current()
    for name, value in settings.items():
        setattr(season, name, value)
    if started:
        season.started_at = timezone.now()
    season.save()
    return season


def singles(season, count, sex="M", prefix="P"):
    """Create ``count`` singles entries with alphabetically ordered names."""
    return [
        services.create_entry(season, make_user(first=prefix, last=f"{prefix}{i:02d}", sex=sex))
        for i in range(count)
    ]


def place(season, entries, name):
    services.assign_groups(season, entries[0].tournament, {e: name for e in entries})
    for entry in entries:
        entry.refresh_from_db()


def group_match(entry_a, entry_b):
    a, b = sorted([entry_a.pk, entry_b.pk])
    return Match.objects.get(stage=Match.Stage.GROUP, entry1_id=a, entry2_id=b)


def win(match, winner, user=None):
    """Record a 6:0 6:0 win for ``winner``."""
    sets = [(6, 0), (6, 0)] if winner.pk == match.entry1_id else [(0, 6), (0, 6)]
    services.record_result(match, sets, user or winner.player1)


def play_round_robin(entries):
    """Earlier entries in the list beat later ones."""
    for i, a in enumerate(entries):
        for b in entries[i + 1:]:
            win(group_match(a, b), a)
