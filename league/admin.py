from django.contrib import admin

from .models import Entry, Group, Match, Season


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ["year", "name", "best_of", "games_per_set", "deciding_match_tiebreak", "started_at"]


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ["season", "tournament", "name"]
    list_filter = ["season", "tournament"]


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ["__str__", "season", "tournament", "group", "created_at", "withdrawn_at"]
    list_filter = ["season", "tournament", "group__name"]
    search_fields = ["player1__last_name", "player1__first_name", "player2__last_name", "player2__first_name"]
    autocomplete_fields = ["player1", "player2", "created_by"]
    list_select_related = ["player1", "player2", "group"]


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ["__str__", "season", "tournament", "stage", "group", "slot", "status", "score"]
    list_filter = ["season", "tournament", "stage", "status"]
    raw_id_fields = ["entry1", "entry2", "winner"]
    readonly_fields = ["reported_at"]
    list_select_related = ["entry1__player1", "entry1__player2", "entry2__player1", "entry2__player2", "group"]
