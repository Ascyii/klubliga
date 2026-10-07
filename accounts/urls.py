from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("login/code/", views.code_view, name="code"),
    path("login/resend/", views.resend_view, name="resend"),
    path("login/link/<str:secret>/", views.link_view, name="link"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
]
