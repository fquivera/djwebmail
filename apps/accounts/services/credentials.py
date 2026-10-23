"""Encrypted, server-side storage for transient IMAP credentials.

The password never enters the Django session, the database, or the browser.
It is encrypted with Fernet and stored in the cache under the opaque Django
session key. Production uses Redis; development and tests use a local cache.
"""

from __future__ import annotations

import hashlib
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.cache import cache

from apps.accounts.constants import CREDENTIAL_CACHE_PREFIX
from apps.accounts.exceptions import MailConfigurationError, MailSessionError


class CredentialStore:
    """Store and retrieve one encrypted password per server-side session."""

    def __init__(
        self,
        *,
        cache_backend: Any | None = None,
        fernet_key: str | None = None,
        ttl: int | None = None,
    ) -> None:
        self._cache = cache_backend if cache_backend is not None else cache
        self._ttl = ttl if ttl is not None else settings.SESSION_COOKIE_AGE
        if self._ttl <= 0:
            raise MailConfigurationError("DJANGO_SESSION_COOKIE_AGE must be positive")
        self._fernet = self._build_fernet(fernet_key)

    def save(self, session_key: str, password: str) -> None:
        """Encrypt and store the password for ``session_key``."""
        if not session_key:
            raise MailSessionError("Cannot store a credential without a session key")
        if not password:
            raise MailSessionError("Cannot store an empty credential")
        token = self._fernet.encrypt(password.encode("utf-8")).decode("ascii")
        self._cache.set(self._cache_key(session_key), token, timeout=self._ttl)

    def load(self, session_key: str) -> str | None:
        """Return the decrypted password, or ``None`` when absent/invalid."""
        if not session_key:
            return None
        token = self._cache.get(self._cache_key(session_key))
        if not isinstance(token, str):
            return None
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError, ValueError):
            self.delete(session_key)
            return None

    def delete(self, session_key: str) -> None:
        """Remove the stored credential, if any."""
        if session_key:
            self._cache.delete(self._cache_key(session_key))

    @staticmethod
    def _cache_key(session_key: str) -> str:
        digest = hashlib.sha256(session_key.encode("utf-8")).hexdigest()
        return f"{CREDENTIAL_CACHE_PREFIX}{digest}"

    @staticmethod
    def _build_fernet(fernet_key: str | None) -> Fernet:
        key = fernet_key if fernet_key is not None else settings.FERNET_KEY
        if not key:
            raise MailConfigurationError(
                "FERNET_KEY is not configured; generate one before enabling login"
            )
        try:
            return Fernet(key.encode("ascii"))
        except (TypeError, UnicodeError, ValueError) as exc:
            raise MailConfigurationError("FERNET_KEY is not a valid Fernet key") from exc
