"""Admin registration for internal inspection of mail preferences."""

from django.contrib import admin

from apps.preferences.models import MailPreference


@admin.register(MailPreference)
class MailPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "account_key",
        "language",
        "theme",
        "density",
        "page_size",
        "updated_at",
    )
    list_filter = ("theme", "density", "layout", "remote_images")
    search_fields = ("email", "account_key")
    readonly_fields = ("account_key", "email", "created_at", "updated_at")
