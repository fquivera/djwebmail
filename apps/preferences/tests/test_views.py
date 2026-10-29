"""Tests for the preferences page and HTMX save flow."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import translation

from apps.accounts.services.account import MailAccount
from apps.preferences.constants import Density, Theme
from apps.preferences.models import MailPreference

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def reset_translation():
    translation.deactivate()
    yield
    translation.deactivate()


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


@pytest.fixture
def preference(account: MailAccount) -> MailPreference:
    return cast(Any, MailPreference).objects.create(
        account_key=account.account_key,
        email=account.email,
        language="en",
        timezone="UTC",
        theme=Theme.SYSTEM,
        density=Density.COMPACT,
        page_size=50,
    )


@pytest.fixture
def logged_in_client(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    account: MailAccount,
) -> Client:
    monkeypatch.setattr(
        "apps.accounts.middleware.load_mail_account",
        lambda request: account,
    )
    monkeypatch.setattr(
        "apps.accounts.middleware.activate_session_timezone",
        lambda request: None,
    )
    session = client.session
    session["mail_email"] = account.email
    session.save()
    return client


def valid_data(**overrides: str) -> dict[str, str]:
    data = {
        "language": "es",
        "timezone": "Europe/Madrid",
        "theme": Theme.DARK,
        "density": Density.COMFORTABLE,
        "page_size": "25",
    }
    data.update(overrides)
    return data


def test_settings_requires_login(client: Client) -> None:
    response: Any = client.get(reverse("preferences:index"))

    assert response.status_code == 302
    assert response["Location"] == f"{reverse('accounts:login')}?next=%2Fsettings%2F"


def test_settings_renders_full_page(
    logged_in_client: Client,
    preference: MailPreference,
) -> None:
    response: Any = logged_in_client.get(reverse("preferences:index"))

    assert response.status_code == 200
    assert b'id="settings-form"' in response.content
    assert b"user@example.com" in response.content
    assert b'name="language"' in response.content
    assert b'name="timezone"' in response.content
    assert b'name="theme"' in response.content
    assert b'name="density"' in response.content
    assert b'name="page_size"' in response.content
    assert b'aria-describedby="id_page_size_help"' in response.content
    assert b'id="id_page_size_help"' in response.content


def test_settings_htmx_request_returns_partial(
    logged_in_client: Client,
    preference: MailPreference,
) -> None:
    response: Any = logged_in_client.get(
        reverse("preferences:index"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b'id="settings-form"' in response.content
    assert b"<html" not in response.content
    assert "HX-Request" in response["Vary"]


def test_settings_non_htmx_save_redirects_and_updates(
    logged_in_client: Client,
    preference: MailPreference,
) -> None:
    response: Any = logged_in_client.post(reverse("preferences:index"), valid_data())

    assert response.status_code == 302
    assert response["Location"] == reverse("preferences:index")

    preference.refresh_from_db()
    assert preference.language == "es"
    assert preference.timezone == "Europe/Madrid"
    assert preference.theme == Theme.DARK
    assert preference.density == Density.COMFORTABLE
    assert preference.page_size == 25


def test_settings_renders_in_saved_language(
    logged_in_client: Client,
    preference: MailPreference,
) -> None:
    preference.language = "es"
    preference.save(update_fields=["language"])
    session = logged_in_client.session
    session["mail_language"] = "es"
    session.save()

    response: Any = logged_in_client.get(reverse("preferences:index"))

    assert response.status_code == 200
    assert b"Idioma" in response.content
    assert b"Zona horaria" in response.content
    assert b"Guardar preferencias" in response.content
    assert b'<html\n  lang="es"' in response.content


def test_settings_htmx_save_returns_partial_and_trigger(
    logged_in_client: Client,
    preference: MailPreference,
) -> None:
    response: Any = logged_in_client.post(
        reverse("preferences:index"),
        valid_data(),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b'id="settings-form"' in response.content
    assert b"Preferencias guardadas." in response.content
    trigger = json.loads(response["HX-Trigger"])
    assert trigger["mail:preference-changed"] == {
        "theme": Theme.DARK,
        "density": Density.COMFORTABLE,
    }
    assert response["HX-Refresh"] == "true"


def test_settings_save_updates_session(
    logged_in_client: Client,
    preference: MailPreference,
) -> None:
    logged_in_client.post(reverse("preferences:index"), valid_data())

    session = logged_in_client.session
    assert session["mail_language"] == "es"
    assert session["mail_theme"] == Theme.DARK
    assert session["mail_density"] == Density.COMFORTABLE
    assert session["mail_timezone"] == "Europe/Madrid"
    assert session["mail_page_size"] == 25


def test_settings_invalid_htmx_save_returns_200_with_errors(
    logged_in_client: Client,
    preference: MailPreference,
) -> None:
    response: Any = logged_in_client.post(
        reverse("preferences:index"),
        valid_data(page_size="0"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Page size must be between" in response.content
    preference.refresh_from_db()
    assert preference.page_size == 50


def test_settings_invalid_non_htmx_save_returns_422(
    logged_in_client: Client,
    preference: MailPreference,
) -> None:
    response: Any = logged_in_client.post(
        reverse("preferences:index"),
        valid_data(page_size="0"),
    )

    assert response.status_code == 422
    assert b"Page size must be between" in response.content


def test_base_applies_theme_and_density_from_session(
    logged_in_client: Client,
    preference: MailPreference,
) -> None:
    session = logged_in_client.session
    session["mail_theme"] = Theme.DARK
    session["mail_density"] = Density.COMFORTABLE
    session.save()

    response: Any = logged_in_client.get(reverse("home"))

    assert response.status_code == 200
    assert b'data-theme="mail-dark"' in response.content
    assert b'data-density="comfortable"' in response.content


def test_base_has_skip_link_and_main_landmark(logged_in_client: Client) -> None:
    response: Any = logged_in_client.get(reverse("home"))

    assert response.status_code == 200
    assert b'href="#main-content"' in response.content
    assert b'id="main-content"' in response.content
    assert b"Skip to main content" in response.content


def test_settings_link_is_visible_for_authenticated_users(
    logged_in_client: Client,
    preference: MailPreference,
) -> None:
    response: Any = logged_in_client.get(reverse("home"))

    assert response.status_code == 200
    assert reverse("preferences:index").encode() in response.content
    assert b"Settings" in response.content


def test_preference_is_created_when_missing(
    logged_in_client: Client,
    account: MailAccount,
) -> None:
    cast(Any, MailPreference).objects.all().delete()

    response: Any = logged_in_client.get(reverse("preferences:index"))

    assert response.status_code == 200
    assert cast(Any, MailPreference).objects.filter(account_key=account.account_key).exists()


def test_settings_saves_signature_and_remote_images_policy(
    logged_in_client: Client,
    preference: MailPreference,
) -> None:
    data = valid_data(remote_images="always", signature_html="Best,\nUser")

    response: Any = logged_in_client.post(reverse("preferences:index"), data)

    assert response.status_code == 302
    preference.refresh_from_db()
    assert preference.remote_images == "always"
    assert preference.signature_html == "Best,\nUser"
    session = logged_in_client.session
    assert session["mail_remote_images"] == "always"
    assert session["mail_signature"] == "Best,\nUser"


def test_settings_saves_owner_name_and_label_and_refreshes_navbar_oob(
    logged_in_client: Client,
    preference: MailPreference,
) -> None:
    data = valid_data(display_name="Alice Smith", account_label="Condominio")

    response: Any = logged_in_client.post(
        reverse("preferences:index"),
        data,
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    preference.refresh_from_db()
    assert preference.display_name == "Alice Smith"
    assert preference.account_label == "Condominio"
    session = logged_in_client.session
    assert session["mail_display_name"] == "Alice Smith"
    assert session["mail_account_label"] == "Condominio"
    assert b'id="navbar-identity"' in response.content
    assert b'hx-swap-oob="outerHTML"' in response.content
    assert b"Alice Smith" in response.content
    assert b"Condominio" in response.content


def test_password_change_requires_login(client: Client) -> None:
    response: Any = client.post(reverse("preferences:password"), {})
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("accounts:login"))


def test_password_change_renders_validation_error_on_mismatch(
    logged_in_client: Client,
    preference: MailPreference,
) -> None:
    response: Any = logged_in_client.post(
        reverse("preferences:password"),
        {
            "current_password": "secret",
            "new_password": "StrongPassword!2026",
            "confirm_password": "DifferentPassword!2026",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"passwords do not match" in response.content.lower()


def test_password_change_succeeds_and_renders_success_alert(
    logged_in_client: Client,
    preference: MailPreference,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    changed: dict[str, str] = {}

    def fake_change(request: Any, current: str, new_pass: str) -> None:
        changed["current"] = current
        changed["new"] = new_pass

    monkeypatch.setattr("apps.preferences.views.change_account_password", fake_change)

    response: Any = logged_in_client.post(
        reverse("preferences:password"),
        {
            "current_password": "secret",
            "new_password": "NewStrongPassword!2026",
            "confirm_password": "NewStrongPassword!2026",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert changed == {"current": "secret", "new": "NewStrongPassword!2026"}
    assert b"Password changed successfully." in response.content


def test_settings_renders_section_dropdown_and_switches_section(
    logged_in_client: Client,
    preference: MailPreference,
) -> None:
    response: Any = logged_in_client.get(reverse("preferences:index"))
    assert response.status_code == 200
    assert b'id="settings-section-selector"' in response.content
    assert b'id="section-preferences"' in response.content
    assert b'id="section-password"' in response.content

    resp_pass: Any = logged_in_client.get(reverse("preferences:index") + "?section=password")
    assert resp_pass.status_code == 200
    content = resp_pass.content.decode("utf-8")
    assert 'id="settings-section-selector"' in content
    assert 'value="password" selected' in content
