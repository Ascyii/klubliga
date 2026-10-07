from django.contrib import admin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import LoginToken, User


def admin_login(request, extra_context=None):
    """The Django admin uses the app's password-less login."""
    if request.user.is_authenticated:
        raise PermissionDenied
    return redirect_to_login(request.get_full_path())


admin.site.login = admin_login


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["email", "last_name", "first_name", "sex", "is_staff", "last_login"]
    list_filter = ["sex", "is_staff", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    fields = ["email", "first_name", "last_name", "sex", "is_active", "is_staff",
              "is_superuser", "last_login", "date_joined"]
    readonly_fields = ["last_login", "date_joined"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.set_unusable_password()
        super().save_model(request, obj, form, change)


@admin.register(LoginToken)
class LoginTokenAdmin(admin.ModelAdmin):
    list_display = ["user", "created_at", "expires_at", "used_at", "attempts"]
    readonly_fields = ["user", "code_hash", "link_hash", "created_at", "expires_at", "used_at", "attempts"]
