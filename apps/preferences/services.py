"""Read and apply per-account presentation preferences."""

from __future__ import annotations

from typing import Any, cast

from django.http import HttpRequest
from django.utils import timezone, translation

from apps.accounts.constants import (
    SESSION_DENSITY_KEY,
    SESSION_LANGUAGE_KEY,
    SESSION_PAGE_SIZE_KEY,
    SESSION_THEME_KEY,
    SESSION_TIMEZONE_KEY,
)
from apps.accounts.exceptions import MailSessionError
from apps.preferences.models import MailPreference


def get_mail_preference(request: HttpRequest) -> MailPreference:
    """Return the preference row for the authenticated account."""
    account = getattr(request, "mail_account", None)
    if account is None:
        raise MailSessionError("No authenticated mail account on this request")
    preference, _created = cast(Any, MailPreference).objects.get_or_create(
        account_key=account.account_key,
        defaults={"email": account.email},
    )
    return preference


def apply_mail_preference(request: HttpRequest, preference: MailPreference) -> None:
    """Copy the saved choices into the session and activate locale settings."""
    session = _session(request)
    session[SESSION_LANGUAGE_KEY] = preference.language
    session[SESSION_THEME_KEY] = preference.theme
    session[SESSION_DENSITY_KEY] = preference.density
    session[SESSION_TIMEZONE_KEY] = preference.timezone
    session[SESSION_PAGE_SIZE_KEY] = preference.page_size
    translation.activate(preference.language)
    setattr(request, "LANGUAGE_CODE", preference.language)  # noqa: B010
    try:
        timezone.activate(preference.timezone)
    except (KeyError, ValueError):
        timezone.deactivate()


def _session(request: HttpRequest) -> Any:
    return cast(Any, request).session
