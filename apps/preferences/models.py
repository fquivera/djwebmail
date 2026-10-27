"""Per-account presentation preferences.

Mail itself lives in IMAP. This model stores only the small set of choices
needed to render the webmail for one account.
"""

from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.accounts.constants import ACCOUNT_KEY_MAX_LENGTH
from apps.preferences.constants import (
    ACCOUNT_LABEL_MAX_LENGTH,
    DISPLAY_NAME_MAX_LENGTH,
    PAGE_SIZE_MIN,
    Density,
    Layout,
    RemoteImages,
    Theme,
)


def default_language() -> str:
    """Use the deployment fallback language, without its region suffix."""
    return settings.LANGUAGE_CODE.split("-", 1)[0]


def default_timezone() -> str:
    return settings.TIME_ZONE


def default_page_size() -> int:
    return settings.MAIL_DEFAULT_PAGE_SIZE


class MailPreference(models.Model):
    # Pyright cannot infer Django field descriptors without django-stubs; cast
    # each field to the Python type the descriptor returns at runtime.
    account_key = cast(str, models.CharField(max_length=ACCOUNT_KEY_MAX_LENGTH, unique=True))
    email = cast(str, models.EmailField(db_index=True))
    display_name = cast(
        str,
        models.CharField(max_length=DISPLAY_NAME_MAX_LENGTH, blank=True, default=""),
    )
    account_label = cast(
        str,
        models.CharField(max_length=ACCOUNT_LABEL_MAX_LENGTH, blank=True, default=""),
    )
    language = cast(str, models.CharField(max_length=8, default=default_language))
    timezone = cast(str, models.CharField(max_length=64, default=default_timezone))
    theme = cast(
        str,
        models.CharField(max_length=8, choices=Theme.choices, default=Theme.SYSTEM),
    )
    density = cast(
        str,
        models.CharField(
            max_length=16,
            choices=Density.choices,
            default=Density.COMPACT,
        ),
    )
    layout = cast(
        str,
        models.CharField(max_length=8, choices=Layout.choices, default=Layout.SIDE),
    )
    page_size = cast(
        int,
        models.PositiveSmallIntegerField(default=default_page_size),  # pyright: ignore[reportArgumentType]
    )
    use_threads = cast(
        bool,
        models.BooleanField(default=False),  # pyright: ignore[reportArgumentType]
    )
    html_allowed = cast(
        bool,
        models.BooleanField(default=True),  # pyright: ignore[reportArgumentType]
    )
    remote_images = cast(
        str,
        models.CharField(
            max_length=8,
            choices=RemoteImages.choices,
            default=RemoteImages.ASK,
        ),
    )
    signature_html = cast(str, models.TextField(blank=True))
    special_folders = cast(dict[str, Any], models.JSONField(default=dict, blank=True))
    created_at = cast(datetime, models.DateTimeField(auto_now_add=True))
    updated_at = cast(datetime, models.DateTimeField(auto_now=True))

    class Meta:
        ordering = ["email"]
        verbose_name = gettext_lazy("mail preference")
        verbose_name_plural = gettext_lazy("mail preferences")

    def __str__(self) -> str:
        return self.email

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        available_languages = {code for code, _name in settings.LANGUAGES}
        if self.language not in available_languages:
            errors["language"] = _("Select a language available in this deployment.")

        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            errors["timezone"] = _("Select a valid time zone.")

        if not PAGE_SIZE_MIN <= self.page_size <= settings.MAIL_MAX_PAGE_SIZE:
            errors["page_size"] = _("Page size must be between %(minimum)s and %(maximum)s.") % {
                "minimum": PAGE_SIZE_MIN,
                "maximum": settings.MAIL_MAX_PAGE_SIZE,
            }

        if "\r" in self.display_name or "\n" in self.display_name:
            errors["display_name"] = _("This field cannot contain line breaks.")

        if "\r" in self.account_label or "\n" in self.account_label:
            errors["account_label"] = _("This field cannot contain line breaks.")

        if errors:
            raise ValidationError(errors)
