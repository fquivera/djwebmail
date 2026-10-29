"""Integration tests for IMAP login, logout, and session expiry."""

from __future__ import annotations

import time
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import pytest
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.views import View

from apps.accounts.exceptions import ImapAuthError
from apps.accounts.mixins import MailLoginRequiredMixin
from apps.accounts.services.account import MailAccount
from apps.accounts.services.credentials import CredentialStore
from apps.preferences.models import MailPreference

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def mail_settings(settings):
    settings.MAIL_DOMAIN = "example.com"
    settings.MAIL_IMAP_HOST = "imap.example.com"
    settings.MAIL_SMTP_HOST = "smtp.example.com"


@pytest.fixture
def account() -> MailAccount:
    return MailAccount(
        email="user@example.com",
        domain="example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_security="ssl",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_security="starttls",
    )


def patch_success(monkeypatch: pytest.MonkeyPatch, account: MailAccount) -> None:
    monkeypatch.setattr(
        "apps.accounts.views.authenticate_mail_account",
        lambda email, password: account,
    )


def patch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(email: str, password: str) -> MailAccount:
        raise ImapAuthError("invalid credentials")

    monkeypatch.setattr("apps.accounts.views.authenticate_mail_account", fail)


def test_login_page_renders(client):
    response = client.get(reverse("accounts:login"))

    assert response.status_code == 200
    assert b"Sign in" in response.content


def test_login_success_creates_session_and_encrypted_credential(client, monkeypatch, account):
    patch_success(monkeypatch, account)

    response = client.post(
        reverse("accounts:login"),
        {"email": "user@example.com", "password": "secret"},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("mail:index")
    session = client.session
    assert session["mail_email"] == "user@example.com"
    assert session["mail_account_key"] == account.account_key
    assert session["mail_theme"] == "system"
    assert session["mail_density"] == "compact"
    assert session["mail_timezone"] == "UTC"
    assert session["mail_page_size"] == settings.MAIL_DEFAULT_PAGE_SIZE
    assert "secret" not in str(dict(session))

    credential_key = CredentialStore._cache_key(session.session_key)
    assert "secret" not in cache.get(credential_key)
    assert CredentialStore().load(session.session_key) == "secret"

    preference = cast(Any, MailPreference).objects.get(account_key=account.account_key)
    assert preference.email == "user@example.com"
    assert preference.language == "en"


def test_login_initializes_preference_from_request_language(client, monkeypatch, account):
    patch_success(monkeypatch, account)

    response = client.post(
        reverse("accounts:login"),
        {"email": "user@example.com", "password": "secret"},
        HTTP_ACCEPT_LANGUAGE="es",
    )

    assert response.status_code == 302
    preference = cast(Any, MailPreference).objects.get(account_key=account.account_key)
    assert preference.language == "es"
    assert client.session["mail_language"] == "es"


def test_authenticated_session_is_hydrated_on_next_request(client, monkeypatch, account):
    patch_success(monkeypatch, account)
    client.post(
        reverse("accounts:login"),
        {"email": "user@example.com", "password": "secret"},
    )

    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert b"user@example.com" in response.content


def test_login_failure_does_not_create_session_or_preference(client, monkeypatch):
    patch_failure(monkeypatch)

    response = client.post(
        reverse("accounts:login"),
        {"email": "user@example.com", "password": "wrong"},
    )

    assert response.status_code == 200
    assert b"Invalid email or password." in response.content
    assert client.session.get("mail_email") is None
    assert cast(Any, MailPreference).objects.count() == 0


@override_settings(MAIL_LOGIN_MAX_ATTEMPTS=1)
def test_login_is_throttled_after_failure(client, monkeypatch):
    patch_failure(monkeypatch)

    first = client.post(
        reverse("accounts:login"),
        {"email": "user@example.com", "password": "wrong"},
    )
    second = client.post(
        reverse("accounts:login"),
        {"email": "user@example.com", "password": "wrong"},
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert b"Too many failed attempts" in second.content


def test_login_accepts_safe_next(client, monkeypatch, account):
    patch_success(monkeypatch, account)

    response = client.post(
        reverse("accounts:login"),
        {
            "email": "user@example.com",
            "password": "secret",
            "next": "/mail/",
        },
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("mail:index")


def test_login_rejects_external_next(client, monkeypatch, account):
    patch_success(monkeypatch, account)

    response = client.post(
        reverse("accounts:login"),
        {
            "email": "user@example.com",
            "password": "secret",
            "next": "https://evil.example/phish",
        },
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("mail:index")


def test_logout_deletes_credential_and_flushes_session(client, monkeypatch, account):
    patch_success(monkeypatch, account)
    client.post(
        reverse("accounts:login"),
        {"email": "user@example.com", "password": "secret"},
    )
    session_key = client.session.session_key

    response = client.post(reverse("accounts:logout"))

    assert response.status_code == 302
    assert response["Location"] == reverse("accounts:login")
    assert client.session.get("mail_email") is None
    assert CredentialStore().load(session_key) is None


def test_logout_rejects_get(client):
    response = client.get(reverse("accounts:logout"))

    assert response.status_code == 405


def test_expired_session_is_flushed(client):
    session = client.session
    session["mail_email"] = "user@example.com"
    session["mail_expires_at"] = int(time.time()) - 1
    session.save()

    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert client.session.get("mail_email") is None


class ProtectedView(MailLoginRequiredMixin, View):
    def get(self, request):
        return HttpResponse(b"ok")


def test_mail_login_required_mixin_redirects():
    request = RequestFactory().get("/protected/")

    response = ProtectedView.as_view()(request)

    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]
    query = parse_qs(urlparse(response["Location"]).query)
    assert query["next"] == ["/protected/"]


def test_mail_login_required_mixin_allows_mail_session():
    request = RequestFactory().get("/protected/")
    setattr(request, "mail_account", object())  # noqa: B010

    response = ProtectedView.as_view()(request)

    assert response.status_code == 200
    assert response.content == b"ok"


def test_login_page_renders_corporate_identity(client: Any) -> None:
    from apps.mailadmin.models import CorporateIdentity

    identity = cast(Any, CorporateIdentity.get_solo())
    identity.organization_name = "Condominio Bella Vista"
    identity.tagline = "Portal de Correo Residencial"
    identity.support_email = "soporte@bellavista.test"
    identity.terms_url = "https://bellavista.test/terminos"
    identity.save()

    response = client.get(reverse("accounts:login"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Condominio Bella Vista" in content
    assert "Portal de Correo Residencial" in content
    assert "soporte@bellavista.test" in content
    assert "https://bellavista.test/terminos" in content
