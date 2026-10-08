from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.utils.translation import gettext as _, ngettext
from django.views.decorators.http import require_POST

from . import services
from .forms import EntryForm, ResultForm, SeasonForm
from .models import Entry, Group, Match, Season, Tournament
from .scoring import ScoreError
from .services import LeagueError

STAGE_ORDER = {Match.Stage.GROUP: 0, Match.Stage.SEMI: 1, Match.Stage.FINAL: 2}
SESSION_TOURNAMENT = "tournament"


def admin_required(view):
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper


def _redirect_next(request, default):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
        return redirect(next_url)
    return redirect(default)


def _pick_tournament(request):
    """The tournament asked for in ``?t=``, else the one opened last on this device.

    Returns None if there is neither.
    """
    tournament = request.GET.get("t")
    if tournament in Tournament.values:
        request.session[SESSION_TOURNAMENT] = tournament
        return tournament
    remembered = request.session.get(SESSION_TOURNAMENT)
    return remembered if remembered in Tournament.values else None


def _mark_mine(rows, user):
    for row in rows:
        row.is_mine = row.entry.has_player(user)
    return rows


def _match_sort_key(match):
    return (STAGE_ORDER[match.stage], match.group.name if match.group_id else "", match.slot, match.pk)


@login_required
def home(request):
    season = Season.current()
    user = request.user
    form = EntryForm(request.POST or None, user=user)
    if request.method == "POST" and form.is_valid():
        try:
            entry = services.create_entry(season, user, form.cleaned_data["partner"])
        except LeagueError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, _("You are entered in %(tournament)s.")
                             % {"tournament": entry.get_tournament_display()})
            return redirect("league:home")

    entries = list(
        Entry.objects.filter(season=season).of_player(user)
        .select_related("season", "group", "player1", "player2")
        .order_by("withdrawn_at", "tournament")
    )
    my_groups = []
    for entry in entries:
        entry.can_withdraw = services.can_withdraw(entry)
        if entry.is_active and entry.group_id:
            rows = _mark_mine(services.group_standings(entry.group), user)
            my_groups.append({"group": entry.group, "rows": rows})

    matches = sorted(
        Match.objects.filter(season=season).of_player(user).with_related(),
        key=lambda m: (m.is_resolved, not m.counts, _match_sort_key(m)),
    )
    return render(request, "league/home.html", {
        "form": form,
        "entries": entries,
        "my_groups": my_groups,
        "matches": matches,
        "open_count": sum(1 for m in matches if not m.is_resolved),
        # Shown by app.js while the new entry form is filled in.
        "tournament_previews": {
            code: _("Tournament: %(tournament)s") % {"tournament": label} for code, label in Tournament.choices
        },
    })


@login_required
@require_POST
def withdraw(request, pk):
    entry = get_object_or_404(Entry.objects.select_related("season"), pk=pk)
    if not (request.user.is_staff or entry.has_player(request.user)):
        raise PermissionDenied
    try:
        services.withdraw_entry(entry)
    except LeagueError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, _("%(entry)s has been withdrawn from %(tournament)s.")
                         % {"entry": entry, "tournament": entry.get_tournament_display()})
    return _redirect_next(request, "league:home")


def _lock_reason(match, user):
    if not match.has_player(user):
        return ""
    if not match.season.is_current:
        return _("This match belongs to a past season.")
    if not match.season.is_started:
        return _("Results can be entered once the league has started.")
    if match.status in (Match.Status.WALKOVER, Match.Status.CANCELLED):
        return _("This result was set by the organiser.")
    if not match.counts:
        return _("This match no longer counts because an entry withdrew or moved.")
    return _("The next round already has a result – please ask the organiser for corrections.")


@login_required
def match_detail(request, pk):
    match = get_object_or_404(Match.objects.with_related(), pk=pk)
    user = request.user
    can_edit = services.can_edit_result(match, user)
    form = None
    if can_edit:
        form = ResultForm(request.POST or None, match=match, admin=user.is_staff)
        if request.method == "POST" and form.is_valid():
            outcome = form.cleaned_data.get("outcome", "played")
            try:
                if outcome == "played":
                    services.record_result(match, form.cleaned_data["sets"], user)
                elif outcome in ("w1", "w2"):
                    services.record_walkover(match, match.entry1 if outcome == "w1" else match.entry2, user)
                elif outcome == "cancelled":
                    services.cancel_match(match, user)
                else:
                    services.reset_match(match, user)
            except (LeagueError, ScoreError) as error:
                form.add_error(None, str(error))
            else:
                messages.success(request, _("The result has been saved."))
                return _redirect_next(request, reverse("league:match", args=[match.pk]))
    elif request.method == "POST":
        raise PermissionDenied

    return render(request, "league/match.html", {
        "match": match,
        "form": form,
        "lock_reason": "" if can_edit else _lock_reason(match, user),
        "is_participant": match.has_player(user),
        "sides": [(match.entry1, match.entry1.players), (match.entry2, match.entry2.players)],
        "tie_break_label": _("to %(points)s") % {"points": match.season.match_tiebreak_points},
    })


def _group_overview(group, user):
    entries = list(group.active_entries())
    matches = services.counting_matches(group, entries)
    return {
        "group": group,
        "rows": _mark_mine(services.group_standings(group, entries, matches), user),
        "complete": services.group_is_complete(group, entries, matches),
        "open": sum(1 for m in matches if not m.is_resolved),
    }


@login_required
def matches(request):
    user = request.user
    current = Season.current()
    seasons = list(Season.objects.all())
    season = next((s for s in seasons if str(s.year) == request.GET.get("season")), current)

    tournament = _pick_tournament(request)
    if tournament is None:
        mine = (
            Entry.objects.active().filter(season=season).of_player(user)
            .order_by("tournament").values_list("tournament", flat=True).first()
        )
        tournament = mine or Tournament.MEN_SINGLES

    groups = [_group_overview(g, user) for g in services.active_groups(season, tournament)]
    knockout = {(m.stage, m.slot): m for m in Match.objects.filter(
        season=season, tournament=tournament, stage__in=services.KNOCKOUT_STAGES).with_related()}
    bracket = [
        {"title": title, "match": knockout.get((stage, slot)), "label1": label1, "label2": label2}
        for stage, slot, title, label1, label2 in services.knockout_layout(len(groups))
    ]

    filters = {
        "stage": request.GET.get("stage", ""),
        "status": request.GET.get("status", ""),
        "q": request.GET.get("q", "").strip(),
        "mine": request.GET.get("mine") == "1",
    }
    qs = Match.objects.filter(season=season, tournament=tournament).with_related()
    if filters["stage"] in ("A", "B"):
        qs = qs.filter(stage=Match.Stage.GROUP, group__name=filters["stage"])
    elif filters["stage"] == "ko":
        qs = qs.filter(stage__in=services.KNOCKOUT_STAGES)
    if filters["status"] == "open":
        qs = qs.filter(status=Match.Status.PENDING)
    elif filters["status"] == "done":
        qs = qs.exclude(status=Match.Status.PENDING)
    if filters["mine"]:
        qs = qs.of_player(user)
    if filters["q"]:
        q = Q()
        for side in ("entry1", "entry2"):
            for player in ("player1", "player2"):
                for name in ("first_name", "last_name"):
                    q |= Q(**{f"{side}__{player}__{name}__icontains": filters["q"]})
        qs = qs.filter(q)
    match_list = sorted(qs, key=_match_sort_key)

    return render(request, "league/matches.html", {
        "view_season": season,
        "seasons": seasons,
        "tournament": tournament,
        "tournament_label": Tournament(tournament).label,
        "tournaments": Tournament.choices,
        "groups": groups,
        "bracket": bracket,
        "match_list": match_list,
        "filters": filters,
        "group_names": [g["group"].name for g in groups],
        "any_open_group": any(not g["complete"] and g["open"] for g in groups),
        "can_manage": user.is_staff and season.is_current,
    })


@admin_required
@require_POST
def close(request):
    season = Season.current()
    scope = request.POST.get("scope")
    if scope == "group":
        group = get_object_or_404(Group, pk=request.POST.get("group"), season=season)
        count = services.close_groups([group], request.user)
        what = str(group)
    elif scope == "tournament" and request.POST.get("tournament") in Tournament.values:
        tournament = request.POST["tournament"]
        count = services.close_tournament(season, tournament, request.user)
        what = Tournament(tournament).label
    elif scope == "all":
        count = services.close_all(season, request.user)
        what = _("all tournaments")
    else:
        raise PermissionDenied
    messages.success(request, ngettext(
        "Group phase closed for %(what)s: %(count)d open match marked as not played.",
        "Group phase closed for %(what)s: %(count)d open matches marked as not played.",
        count,
    ) % {"what": what, "count": count})
    return _redirect_next(request, "league:matches")


@admin_required
def groups(request):
    season = Season.current()
    tournament = _pick_tournament(request) or Tournament.MEN_SINGLES
    entries = list(
        Entry.objects.active().filter(season=season, tournament=tournament)
        .select_related("group", "player1", "player2", "season")
    )
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "save":
                assignment = {}
                for entry in entries:
                    value = request.POST.get(f"entry-{entry.pk}", "")
                    assignment[entry] = value if value in ("A", "B") else None
                changed = services.assign_groups(season, tournament, assignment)
                messages.success(request, ngettext(
                    "Groups saved (%(count)d change).", "Groups saved (%(count)d changes).", changed,
                ) % {"count": changed})
            elif action in ("random1", "random2"):
                services.random_split(season, tournament, int(action[-1]))
                messages.success(request, _("Entries have been split randomly."))
        except LeagueError as error:
            messages.error(request, str(error))
        return redirect(f"{reverse('league:groups')}?{urlencode({'t': tournament})}")

    counts = dict(
        Entry.objects.active().filter(season=season).values_list("tournament")
        .annotate(n=Count("id")).values_list("tournament", "n")
    )
    entries.sort(key=lambda e: (e.group.name if e.group_id else "0", e.name.lower()))
    for entry in entries:
        entry.can_remove = services.can_withdraw(entry)
    return render(request, "league/groups.html", {
        "tournament": tournament,
        "tournament_label": Tournament(tournament).label,
        "tabs": [(code, label, counts.get(code, 0)) for code, label in Tournament.choices],
        "entries": entries,
        "group_sizes": {name: sum(1 for e in entries if e.group_id and e.group.name == name) for name in "AB"},
        "waiting": [e for e in entries if not e.group_id],
        "withdrawn": Entry.objects.filter(season=season, tournament=tournament, withdrawn_at__isnull=False)
        .select_related("player1", "player2"),
        "suggested": services.suggested_group_count(season, len(entries)),
        "has_results": services.has_results(season, tournament),
        "locked": services.knockout_has_results(season, tournament),
    })


@admin_required
def settings_view(request):
    season = Season.current()
    action = request.POST.get("action") if request.method == "POST" else None
    form = SeasonForm(request.POST if action == "save" else None, instance=season)
    if action == "save" and form.is_valid():
        form.save()
        messages.success(request, _("Settings saved."))
        return redirect("league:settings")
    if action == "start":
        try:
            services.start_season(season)
            messages.success(request, _("The league has started. Good luck to everybody!"))
        except LeagueError as error:
            messages.error(request, str(error))
        return redirect("league:settings")

    overview = []
    for code, label in Tournament.choices:
        entries = Entry.objects.active().filter(season=season, tournament=code)
        tournament_matches = Match.objects.filter(season=season, tournament=code)
        overview.append({
            "code": code,
            "label": label,
            "entries": entries.count(),
            "waiting": entries.filter(group__isnull=True).count(),
            "groups": len(services.active_groups(season, code)),
            "open": tournament_matches.filter(status=Match.Status.PENDING).count(),
            "done": tournament_matches.exclude(status=Match.Status.PENDING).count(),
            "final": tournament_matches.filter(stage=Match.Stage.FINAL).first(),
        })
    return render(request, "league/settings.html", {"form": form, "overview": overview})
