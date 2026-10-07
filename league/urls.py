from django.urls import path

from . import views

app_name = "league"

urlpatterns = [
    path("", views.home, name="home"),
    path("entries/<int:pk>/withdraw/", views.withdraw, name="withdraw"),
    path("matches/", views.matches, name="matches"),
    path("matches/<int:pk>/", views.match_detail, name="match"),
    path("matches/close/", views.close, name="close"),
    path("groups/", views.groups, name="groups"),
    path("settings/", views.settings_view, name="settings"),
]
