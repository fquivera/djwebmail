"""Admin registration for contacts inspection."""

from django.contrib import admin

from apps.contacts.models import Contact


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "primary_email",
        "organization",
        "category",
        "account_key",
        "updated_at",
    )
    list_filter = ("category",)
    search_fields = ("full_name", "primary_email", "organization", "account_key")
    readonly_fields = ("account_key", "uid", "jcard", "created_at", "updated_at")
