"""Tests for encrypted credential storage and login throttling."""

from __future__ import annotations

from typing import Any

import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from apps.accounts.exceptions import MailConfigurationError, MailSessionError
from apps.accounts.services.credentials import CredentialStore
from apps.accounts.services.throttle import LoginThrottle


class FakeCache:
    """Small cache double that records values and timeouts."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.timeouts: dict[str, int | None] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any, timeout: int | None = None) -> None:
        self.data[key] = value
        self.timeouts[key] = timeout

    def delete(self, key: str) -> None:
        self.data.pop(key, None)
        self.timeouts.pop(key, None)


@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode()


def test_credential_store_round_trip_and_ttl(fernet_key: str):
    backend = FakeCache()
    store = CredentialStore(cache_backend=backend, fernet_key=fernet_key, ttl=120)

    store.save("session-key", "correct horse battery staple")

    key = CredentialStore._cache_key("session-key")
    assert store.load("session-key") == "correct horse battery staple"
    assert "correct horse battery staple" not in backend.data[key]
    assert backend.timeouts[key] == 120


def test_credential_store_delete(fernet_key: str):
    backend = FakeCache()
    store = CredentialStore(cache_backend=backend, fernet_key=fernet_key)

    store.save("session-key", "secret")
    store.delete("session-key")

    assert store.load("session-key") is None
    assert backend.data == {}


def test_credential_store_rejects_tampered_token(fernet_key: str):
    backend = FakeCache()
    store = CredentialStore(cache_backend=backend, fernet_key=fernet_key)
    store.save("session-key", "secret")
    key = CredentialStore._cache_key("session-key")
    backend.data[key] = "not-a-valid-token"

    assert store.load("session-key") is None
    assert key not in backend.data


def test_credential_store_requires_a_valid_key():
    with pytest.raises(MailConfigurationError):
        CredentialStore(cache_backend=FakeCache(), fernet_key="")

    with pytest.raises(MailConfigurationError):
        CredentialStore(cache_backend=FakeCache(), fernet_key="not-a-fernet-key")


@override_settings(FERNET_KEY="")
def test_credential_store_rejects_missing_settings_key():
    with pytest.raises(MailConfigurationError):
        CredentialStore(cache_backend=FakeCache())


def test_credential_store_requires_session_and_password(fernet_key: str):
    store = CredentialStore(cache_backend=FakeCache(), fernet_key=fernet_key)

    with pytest.raises(MailSessionError):
        store.save("", "secret")
    with pytest.raises(MailSessionError):
        store.save("session-key", "")


def test_login_throttle_blocks_after_limit():
    backend = FakeCache()
    throttle = LoginThrottle(cache_backend=backend, max_attempts=2, window_seconds=60)
    key = LoginThrottle.key("user@example.com", "127.0.0.1")

    assert throttle.is_blocked(key) is False
    assert throttle.record_failure(key) == 1
    assert throttle.is_blocked(key) is False
    assert throttle.record_failure(key) == 2
    assert throttle.is_blocked(key) is True
    assert backend.timeouts[key] == 60

    throttle.clear(key)
    assert throttle.is_blocked(key) is False


def test_login_throttle_key_does_not_contain_email_or_address():
    key = LoginThrottle.key("user@example.com", "127.0.0.1")

    assert "user@example.com" not in key
    assert "127.0.0.1" not in key
