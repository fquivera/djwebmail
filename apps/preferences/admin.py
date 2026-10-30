"""Admin registration for internal inspection of mail preferences."""

from django.contrib import admin

from apps.preferences.models import (
    AccountSignature,
    BlockedSender,
    MailPreference,
    TrustedSender,
)


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


@admin.register(AccountSignature)
class AccountSignatureAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "is_default", "is_active", "updated_at")
    list_filter = ("is_default", "is_active")
    search_fields = ("email", "name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TrustedSender)
class TrustedSenderAdmin(admin.ModelAdmin):
    list_display = ("email", "pattern", "description", "created_at")
    search_fields = ("email", "pattern", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(BlockedSender)
class BlockedSenderAdmin(admin.ModelAdmin):
    list_display = ("email", "pattern", "action", "description", "created_at")
    list_filter = ("action",)
    search_fields = ("email", "pattern", "description")
    readonly_fields = ("created_at", "updated_at")
