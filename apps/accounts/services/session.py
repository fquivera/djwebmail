"""Server-side mail session lifecycle and credential access."""

from __future__ import annotations

import time
from typing import Any, cast

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone, translation

from apps.accounts.constants import (
    SESSION_ACCOUNT_KEY,
    SESSION_ACCOUNT_LABEL_KEY,
    SESSION_AUTHENTICATED_AT_KEY,
    SESSION_DENSITY_KEY,
    SESSION_DISPLAY_NAME_KEY,
    SESSION_EMAIL_KEY,
    SESSION_EXPIRES_AT_KEY,
    SESSION_LANGUAGE_KEY,
    SESSION_PAGE_SIZE_KEY,
    SESSION_REMOTE_IMAGES_KEY,
    SESSION_SIGNATURE_KEY,
    SESSION_THEME_KEY,
    SESSION_TIMEZONE_KEY,
)
from apps.accounts.exceptions import MailError, MailSessionError
from apps.accounts.services.account import MailAccount, resolve_mail_account
from apps.accounts.services.credentials import CredentialStore
from apps.accounts.services.imap import ImapService
from apps.accounts.services.smtp import SmtpService
from apps.preferences.constants import RemoteImages
from apps.preferences.models import MailPreference


def authenticate_mail_account(email: str, password: str) -> MailAccount:
    """Resolve the account and verify the credentials against IMAP."""
    account = resolve_mail_account(email)
    with ImapService(account, account.email, password):
        pass
    return account


def start_mail_session(request: HttpRequest, account: MailAccount, password: str) -> MailPreference:
    """Rotate the session, store the credential, and initialize preferences."""
    session = _session(request)
    session.cycle_key()
    session_key = session.session_key
    if not session_key:
        raise MailSessionError("Django did not create a session key")

    request_language = getattr(request, "LANGUAGE_CODE", "")
    preference, _created = cast(Any, MailPreference).objects.get_or_create(
        account_key=account.account_key,
        defaults={
            "email": account.email,
            "language": _valid_preference_language(request_language),
            "timezone": settings.TIME_ZONE,
        },
    )
    language = _valid_preference_language(preference.language)

    CredentialStore().save(session_key, password)

    now = int(time.time())
    session[SESSION_EMAIL_KEY] = account.email
    session[SESSION_ACCOUNT_KEY] = account.account_key
    session[SESSION_AUTHENTICATED_AT_KEY] = now
    session[SESSION_EXPIRES_AT_KEY] = now + settings.SESSION_COOKIE_AGE
    session[SESSION_LANGUAGE_KEY] = language
    session[SESSION_THEME_KEY] = preference.theme
    session[SESSION_DENSITY_KEY] = preference.density
    session[SESSION_TIMEZONE_KEY] = preference.timezone
    session[SESSION_PAGE_SIZE_KEY] = preference.page_size
    session[SESSION_REMOTE_IMAGES_KEY] = preference.remote_images
    session[SESSION_SIGNATURE_KEY] = preference.signature_html
    session[SESSION_DISPLAY_NAME_KEY] = preference.display_name
    session[SESSION_ACCOUNT_LABEL_KEY] = preference.account_label
    setattr(request, "mail_account", account)  # noqa: B010
    translation.activate(language)
    return preference


def end_mail_session(request: HttpRequest) -> None:
    """Delete the encrypted credential and invalidate the session."""
    session = _session(request)
    session_key = session.session_key
    if session_key:
        try:
            CredentialStore().delete(session_key)
        except MailError:
            pass
    session.flush()
    setattr(request, "mail_account", None)  # noqa: B010


def load_mail_account(request: HttpRequest) -> MailAccount | None:
    """Load the account from the session, enforcing absolute expiry."""
    session = _session(request)
    email = session.get(SESSION_EMAIL_KEY)
    if not isinstance(email, str) or not email:
        return None

    expires_at = session.get(SESSION_EXPIRES_AT_KEY)
    if not isinstance(expires_at, (int, float)) or time.time() >= float(expires_at):
        _invalidate_mail_session(session)
        return None

    try:
        return resolve_mail_account(email)
    except MailError:
        _invalidate_mail_session(session)
        return None


def activate_session_language(request: HttpRequest) -> None:
    """Apply the stored per-account language after LocaleMiddleware."""
    language = _session(request).get(SESSION_LANGUAGE_KEY)
    if isinstance(language, str) and language in _available_languages():
        translation.activate(language)
        setattr(request, "LANGUAGE_CODE", language)  # noqa: B010


def activate_session_timezone(request: HttpRequest) -> None:
    """Apply the stored per-account time zone after LocaleMiddleware."""
    name = _session(request).get(SESSION_TIMEZONE_KEY)
    if isinstance(name, str) and name:
        try:
            timezone.activate(name)
            return
        except (ValueError, KeyError):
            pass
    timezone.deactivate()


def get_mail_page_size(request: HttpRequest) -> int:
    """Return the account page size, clamped to the deployment maximum."""
    maximum = max(1, settings.MAIL_MAX_PAGE_SIZE)
    default = min(max(1, settings.MAIL_DEFAULT_PAGE_SIZE), maximum)
    value = _session(request).get(SESSION_PAGE_SIZE_KEY)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return min(value, maximum)
    return default


def get_mail_remote_images(request: HttpRequest) -> str:
    """Return the account's remote-image policy from the session."""
    value = _session(request).get(SESSION_REMOTE_IMAGES_KEY)
    if isinstance(value, str) and value in RemoteImages.values:
        return value
    return RemoteImages.ASK


def get_mail_signature(request: HttpRequest) -> str:
    """Return the account's signature text from the session."""
    value = _session(request).get(SESSION_SIGNATURE_KEY)
    return value.strip() if isinstance(value, str) else ""


def get_mail_display_name(request: HttpRequest) -> str:
    """Return the account's owner display name from the session."""
    value = _session(request).get(SESSION_DISPLAY_NAME_KEY)
    return value.strip() if isinstance(value, str) else ""


def get_mail_account_label(request: HttpRequest) -> str:
    """Return the account's descriptive label from the session."""
    value = _session(request).get(SESSION_ACCOUNT_LABEL_KEY)
    return value.strip() if isinstance(value, str) else ""


def get_mail_imap_service(request: HttpRequest) -> ImapService:
    """Build a request-scoped IMAP service from the server-side credential."""
    account, password = _mail_credentials(request)
    return ImapService(account, account.email, password)


def get_mail_smtp_service(request: HttpRequest) -> SmtpService:
    """Build a request-scoped SMTP service from the server-side credential."""
    account, password = _mail_credentials(request)
    return SmtpService(account, account.email, password)


def _mail_credentials(request: HttpRequest) -> tuple[MailAccount, str]:
    """Return the authenticated account and its decrypted password."""
    account = getattr(request, "mail_account", None)
    if account is None:
        raise MailSessionError("No authenticated mail account on this request")
    session_key = _session(request).session_key
    if not session_key:
        raise MailSessionError("The mail session has no key")
    password = CredentialStore().load(session_key)
    if not password:
        raise MailSessionError("The mail credential is missing or expired")
    return account, password


def _available_languages() -> set[str]:
    return {code for code, _name in settings.LANGUAGES}


def _default_language() -> str:
    return settings.LANGUAGE_CODE.split("-", 1)[0]


def _valid_preference_language(language: str) -> str:
    return language if language in _available_languages() else _default_language()


def _session(request: HttpRequest) -> Any:
    """Return the session object without requiring django-stubs for pyright."""
    return getattr(request, "session")  # noqa: B009


def _invalidate_mail_session(session: Any) -> None:
    """Delete any encrypted credential before discarding an invalid session."""
    session_key = session.session_key
    if session_key:
        try:
            CredentialStore().delete(session_key)
        except MailError:
            pass
    session.flush()
