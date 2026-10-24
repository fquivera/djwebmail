"""Server-side mail session lifecycle and credential access."""

from __future__ import annotations

import time
from typing import Any, cast

from django.conf import settings
from django.http import HttpRequest
from django.utils import translation

from apps.accounts.constants import (
    SESSION_ACCOUNT_KEY,
    SESSION_AUTHENTICATED_AT_KEY,
    SESSION_EMAIL_KEY,
    SESSION_EXPIRES_AT_KEY,
    SESSION_LANGUAGE_KEY,
)
from apps.accounts.exceptions import MailError, MailSessionError
from apps.accounts.services.account import MailAccount, resolve_mail_account
from apps.accounts.services.credentials import CredentialStore
from apps.accounts.services.imap import ImapService
from apps.accounts.services.smtp import SmtpService
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
