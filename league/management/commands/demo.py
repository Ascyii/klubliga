import random

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import User
from league import services
from league.models import Entry, Group, Match, Season, Tournament

MEN = ["Lukas Bauer", "Jonas Keller", "Felix Wagner", "Paul Schmid", "Leon Huber", "Max Frei",
       "Tim Vogel", "David Roth", "Simon Brunner", "Elias Kunz", "Noah Steiner", "Jan Lang"]
WOMEN = ["Anna Meier", "Lea Fischer", "Laura Weber", "Sara Graf", "Mia Baumann", "Nina Koch",
         "Julia Wolf", "Lena Berger", "Sophie Hofer", "Emma Moser", "Clara Arnold", "Lina Suter"]


def random_sets(rules, rng):
    """A plausible, valid score from the winner's perspective."""
    g = rules.games_per_set
    def regular():
        return rng.choice([(g, rng.randint(0, g - 2)), (g + 1, g - 1), (g + 1, g)])
    sets = [regular()]
    for _ in range(rules.sets_to_win - 1):
        if rng.random() < 0.35:  # the loser takes a set
            sets.append(regular()[::-1])
        sets.append(regular())
    sets = sets[: rules.best_of]
    # The deciding set may have to be a match tie-break.
    if len(sets) == rules.best_of and rules.is_tiebreak_set(len(sets) - 1):
        p = rules.match_tiebreak_points
        sets[-1] = (p, rng.randint(0, p - 2))
    return sets


class Command(BaseCommand):
    help = "Fill the current season with demo members, entries, groups and results."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="delete entries, groups and matches of the current season first")
        parser.add_argument("--results", type=float, default=0.7,
                            help="share of group matches that get a result (default 0.7)")
        parser.add_argument("--seed", type=int, default=None)

    def handle(self, reset=False, results=0.7, seed=None, **options):
        rng = random.Random(seed)
        season = Season.current()
        if Entry.objects.filter(season=season).exists():
            if not reset:
                raise CommandError("The current season already has entries. Use --reset to replace them.")
            Match.objects.filter(season=season).delete()
            Entry.objects.filter(season=season).delete()
            Group.objects.filter(season=season).delete()
            season.started_at = None
            season.save()

        def member(full_name, sex, number):
            first, last = full_name.split()
            user, _ = User.objects.get_or_create(
                email=f"demo{number}@example.com",
                defaults={"first_name": first, "last_name": last, "sex": sex},
            )
            if user.last_login is None:
                user.last_login = timezone.now()
                user.set_unusable_password()
                user.save()
            return user

        men = [member(n, "M", i) for i, n in enumerate(MEN, 1)]
        women = [member(n, "F", i) for i, n in enumerate(WOMEN, 101)]

        for player in men[:10]:
            services.create_entry(season, player)
        for player in women[:5]:
            services.create_entry(season, player)
        for a, b in zip(men[0:8:2], men[1:8:2]):
            services.create_entry(season, a, b)
        for a, b in zip(women[0:6:2], women[1:6:2]):
            services.create_entry(season, a, b)
        for a, b in zip(men[4:10], women[4:10]):
            services.create_entry(season, a, b)

        for code in Tournament.values:
            count = Entry.objects.active().filter(season=season, tournament=code).count()
            services.random_split(season, code, services.suggested_group_count(season, count), rng)
        services.start_season(season)

        rules = season.rules
        played = 0
        for match in Match.objects.filter(season=season, stage=Match.Stage.GROUP).order_by("?"):
            if rng.random() >= results:
                continue
            sets = random_sets(rules, rng)
            if rng.random() < 0.5:
                sets = [(b, a) for a, b in sets]
            services.record_result(match, sets, match.entry1.player1)
            played += 1

        # A late entry waiting for admission.
        services.create_entry(season, women[10])
        self.stdout.write(self.style.SUCCESS(
            f"Season {season.year}: {Entry.objects.filter(season=season).count()} entries, "
            f"{Match.objects.filter(season=season).count()} matches, {played} results."
        ))
        self.stdout.write("Demo members log in with demo1@example.com … demo12@example.com, "
                          "demo101@example.com … demo112@example.com (codes appear in the console).")
