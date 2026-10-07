from django.conf import settings
from django.db import models
from django.utils import timezone

from .scoring import ScoringRules


class Tournament(models.TextChoices):
    """The five tournaments of every season, defined by format and sex."""

    MEN_SINGLES = "MS", "Men's Singles"
    WOMEN_SINGLES = "WS", "Women's Singles"
    MEN_DOUBLES = "MD", "Men's Doubles"
    WOMEN_DOUBLES = "WD", "Women's Doubles"
    MIXED_DOUBLES = "XD", "Mixed Doubles"

    @classmethod
    def for_players(cls, player1, player2=None):
        """Derive the tournament from the players' sex and their number."""
        if player2 is None:
            return cls.MEN_SINGLES if player1.sex == "M" else cls.WOMEN_SINGLES
        sexes = {player1.sex, player2.sex}
        if sexes == {"M"}:
            return cls.MEN_DOUBLES
        if sexes == {"F"}:
            return cls.WOMEN_DOUBLES
        return cls.MIXED_DOUBLES

    @classmethod
    def is_doubles(cls, code):
        return code in (cls.MEN_DOUBLES, cls.WOMEN_DOUBLES, cls.MIXED_DOUBLES)


class Season(models.Model):
    """One year of the league, including the rules it is played with."""

    BEST_OF_CHOICES = [(1, "1 set"), (3, "Best of 3 sets"), (5, "Best of 5 sets")]
    SETTING_FIELDS = [
        "name", "best_of", "games_per_set", "deciding_match_tiebreak",
        "match_tiebreak_points", "two_groups_from",
    ]

    year = models.PositiveIntegerField(unique=True)
    name = models.CharField("league name", max_length=60, default="Klubliga")
    best_of = models.PositiveSmallIntegerField("sets per match", choices=BEST_OF_CHOICES, default=3)
    games_per_set = models.PositiveSmallIntegerField(default=6)
    deciding_match_tiebreak = models.BooleanField(
        "deciding set is a match tie-break", default=True
    )
    match_tiebreak_points = models.PositiveSmallIntegerField("points in the match tie-break", default=10)
    two_groups_from = models.PositiveSmallIntegerField(
        "suggest two groups from", default=8,
        help_text="Number of entries in a tournament from which two groups are suggested.",
    )
    started_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-year"]

    def __str__(self):
        return f"{self.name} {self.year}"

    @classmethod
    def current_year(cls):
        return timezone.localdate().year

    @classmethod
    def current(cls):
        """The season of the current year; created on first use with the
        settings of the most recent earlier season."""
        year = cls.current_year()
        season = cls.objects.filter(year=year).first()
        if season is None:
            previous = cls.objects.filter(year__lt=year).order_by("-year").first()
            defaults = {f: getattr(previous, f) for f in cls.SETTING_FIELDS} if previous else {}
            season, _ = cls.objects.get_or_create(year=year, defaults=defaults)
        return season

    @property
    def is_started(self):
        return self.started_at is not None

    @property
    def is_current(self):
        return self.year == self.current_year()

    @property
    def rules(self):
        return ScoringRules(
            best_of=self.best_of,
            games_per_set=self.games_per_set,
            deciding_match_tiebreak=self.deciding_match_tiebreak,
            match_tiebreak_points=self.match_tiebreak_points,
        )


class Group(models.Model):
    class Name(models.TextChoices):
        A = "A", "Group A"
        B = "B", "Group B"

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="groups")
    tournament = models.CharField(max_length=2, choices=Tournament.choices)
    name = models.CharField(max_length=1, choices=Name.choices)

    class Meta:
        ordering = ["season", "tournament", "name"]
        constraints = [
            models.UniqueConstraint(fields=["season", "tournament", "name"], name="unique_group"),
        ]

    def __str__(self):
        return f"{self.get_tournament_display()} – Group {self.name}"

    def active_entries(self):
        return self.entries.filter(withdrawn_at__isnull=True).select_related("player1", "player2")


class EntryQuerySet(models.QuerySet):
    def active(self):
        return self.filter(withdrawn_at__isnull=True)

    def of_player(self, user):
        return self.filter(models.Q(player1=user) | models.Q(player2=user))


class Entry(models.Model):
    """One or two players taking part in one tournament of a season."""

    class Status(models.TextChoices):
        REGISTERED = "registered", "Registered"
        PLACED = "placed", "Placed in a group"
        WAITING = "waiting", "Waiting for admission"
        WITHDRAWN = "withdrawn", "Withdrawn"

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="entries")
    tournament = models.CharField(max_length=2, choices=Tournament.choices)
    player1 = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entries_as_player1"
    )
    player2 = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entries_as_player2",
        null=True, blank=True,
    )
    group = models.ForeignKey(
        Group, on_delete=models.SET_NULL, related_name="entries", null=True, blank=True
    )
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="+", null=True, blank=True
    )
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    objects = EntryQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "entries"
        ordering = ["season", "tournament", "player1__last_name", "player1__first_name"]

    def __str__(self):
        return self.name

    @property
    def name(self):
        if self.player2_id is None:
            return self.player1.get_full_name()
        return f"{self.player1.short_name} / {self.player2.short_name}"

    @property
    def players(self):
        return [p for p in (self.player1, self.player2) if p is not None]

    def has_player(self, user):
        return user.pk in (self.player1_id, self.player2_id)

    @property
    def is_active(self):
        return self.withdrawn_at is None

    @property
    def status(self):
        if self.withdrawn_at:
            return self.Status.WITHDRAWN
        if self.group_id:
            return self.Status.PLACED
        return self.Status.WAITING if self.season.is_started else self.Status.REGISTERED

    @property
    def status_label(self):
        if self.status == self.Status.PLACED:
            return f"Group {self.group.name}"
        return self.Status(self.status).label


class MatchQuerySet(models.QuerySet):
    def of_player(self, user):
        return self.filter(
            models.Q(entry1__player1=user) | models.Q(entry1__player2=user)
            | models.Q(entry2__player1=user) | models.Q(entry2__player2=user)
        )

    def with_related(self):
        return self.select_related(
            "season", "group", "winner",
            "entry1__player1", "entry1__player2", "entry1__group",
            "entry2__player1", "entry2__player2", "entry2__group",
        )


class Match(models.Model):
    class Stage(models.TextChoices):
        GROUP = "group", "Group"
        SEMI = "semi", "Semi-final"
        FINAL = "final", "Final"

    class Status(models.TextChoices):
        PENDING = "pending", "Open"
        PLAYED = "played", "Played"
        WALKOVER = "walkover", "Walkover"
        CANCELLED = "cancelled", "Not played"

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="matches")
    tournament = models.CharField(max_length=2, choices=Tournament.choices)
    stage = models.CharField(max_length=5, choices=Stage.choices, default=Stage.GROUP)
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="matches", null=True, blank=True
    )
    slot = models.PositiveSmallIntegerField(default=0, help_text="Knockout position (1 or 2).")
    entry1 = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="+")
    entry2 = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.PENDING)
    score = models.CharField(max_length=60, blank=True, help_text="From entry 1's perspective, e.g. 6:4 3:6 10:8")
    winner = models.ForeignKey(Entry, on_delete=models.SET_NULL, related_name="+", null=True, blank=True)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="+", null=True, blank=True
    )
    reported_at = models.DateTimeField(null=True, blank=True)

    objects = MatchQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "matches"
        ordering = ["season", "tournament", "stage", "group__name", "slot", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "entry1", "entry2"],
                condition=models.Q(stage="group"),
                name="unique_group_pairing",
            ),
            models.UniqueConstraint(
                fields=["season", "tournament", "stage", "slot"],
                condition=~models.Q(stage="group"),
                name="unique_knockout_slot",
            ),
        ]

    def __str__(self):
        return f"{self.entry1} vs {self.entry2}"

    @property
    def is_resolved(self):
        return self.status != self.Status.PENDING

    @property
    def is_decided(self):
        return self.status in (self.Status.PLAYED, self.Status.WALKOVER)

    @property
    def is_knockout(self):
        return self.stage != self.Stage.GROUP

    @property
    def counts(self):
        """Group matches count only while both entries are active members of
        the match's group. Knockout matches always count."""
        if self.is_knockout:
            return True
        return all(
            e.withdrawn_at is None and e.group_id == self.group_id
            for e in (self.entry1, self.entry2)
        )

    @property
    def stage_label(self):
        if self.stage == self.Stage.GROUP:
            return f"Group {self.group.name}" if self.group_id else "Group"
        if self.stage == self.Stage.SEMI:
            return f"Semi-final {self.slot}"
        return "Final"

    def has_player(self, user):
        return self.entry1.has_player(user) or self.entry2.has_player(user)

    def sets(self):
        """The score as a list of (games entry1, games entry2) tuples."""
        from .scoring import parse_score
        return parse_score(self.score) if self.score else []

    def score_for(self, entry):
        """The score text from the perspective of ``entry``."""
        if entry == self.entry1 or not self.score:
            return self.score
        return " ".join(f"{b}:{a}" for a, b in self.sets())
