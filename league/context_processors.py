from .models import Season


def league(request):
    season = Season.current()
    return {"season": season, "league_name": season.name}
