"""Cache-backed throttling for failed IMAP login attempts."""

from __future__ import annotations

import hashlib
from typing import Any

from django.conf import settings
from django.core.cache import cache

from apps.accounts.constants import LOGIN_THROTTLE_CACHE_PREFIX
from apps.accounts.exceptions import MailConfigurationError


class LoginThrottle:
    """Count failures per email and remote address inside a time window."""

    def __init__(
        self,
        *,
        cache_backend: Any | None = None,
        max_attempts: int | None = None,
        window_seconds: int | None = None,
    ) -> None:
        self._cache = cache_backend if cache_backend is not None else cache
        self.max_attempts = (
            max_attempts if max_attempts is not None else settings.MAIL_LOGIN_MAX_ATTEMPTS
        )
        self.window_seconds = (
            window_seconds if window_seconds is not None else settings.MAIL_LOGIN_WINDOW_SECONDS
        )
        if self.max_attempts <= 0 or self.window_seconds <= 0:
            raise MailConfigurationError("Login throttle limits must be positive")

    @staticmethod
    def key(email: str, remote_address: str) -> str:
        """Return a privacy-preserving cache key for one login source."""
        digest = hashlib.sha256(
            f"{email.strip().lower()}|{remote_address.strip()}".encode()
        ).hexdigest()
        return f"{LOGIN_THROTTLE_CACHE_PREFIX}{digest}"

    def attempts(self, key: str) -> int:
        value = self._cache.get(key, 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def is_blocked(self, key: str) -> bool:
        return self.attempts(key) >= self.max_attempts

    def record_failure(self, key: str) -> int:
        count = self.attempts(key) + 1
        self._cache.set(key, count, timeout=self.window_seconds)
        return count

    def clear(self, key: str) -> None:
        self._cache.delete(key)
