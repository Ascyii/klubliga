from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),  # set_language: the language switch
    path("", include("accounts.urls")),
    path("", include("league.urls")),
]
