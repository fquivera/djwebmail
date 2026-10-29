"""Tests for mailadmin views."""

from __future__ import annotations

from typing import Any, cast

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.services.account import MailAccount
from apps.mailadmin.models import CorporateIdentity

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_account() -> MailAccount:
    return MailAccount(
        email="admin@example.com",
        domain="example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_security="ssl",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_security="starttls",
    )


@pytest.fixture
def regular_account() -> MailAccount:
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
def admin_client(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    admin_account: MailAccount,
) -> Client:
    monkeypatch.setattr(
        "apps.accounts.middleware.load_mail_account",
        lambda request: admin_account,
    )
    monkeypatch.setattr(
        "apps.accounts.middleware.activate_session_timezone",
        lambda request: None,
    )
    session = client.session
    session["mail_email"] = admin_account.email
    session.save()
    return client


@pytest.fixture
def regular_client(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    regular_account: MailAccount,
) -> Client:
    monkeypatch.setattr(
        "apps.accounts.middleware.load_mail_account",
        lambda request: regular_account,
    )
    monkeypatch.setattr(
        "apps.accounts.middleware.activate_session_timezone",
        lambda request: None,
    )
    session = client.session
    session["mail_email"] = regular_account.email
    session.save()
    return client


@override_settings(MAIL_ADMIN_ACCOUNTS=["admin@example.com"])
def test_admin_index_accessible_by_admin(admin_client: Client) -> None:
    response: Any = admin_client.get(reverse("mailadmin:index"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert (
        "Mail Server Administration" in content
        or "Administración del Servidor de Correo" in content
    )
    assert reverse("mailadmin:branding") in content


@override_settings(MAIL_ADMIN_ACCOUNTS=["admin@example.com"])
def test_admin_index_forbidden_for_regular_user(regular_client: Client) -> None:
    response: Any = regular_client.get(reverse("mailadmin:index"))
    assert response.status_code == 403


def test_admin_index_redirects_anonymous(client: Client) -> None:
    response: Any = client.get(reverse("mailadmin:index"))
    assert response.status_code == 302
    assert "/login/" in response["Location"]


@override_settings(MAIL_ADMIN_ACCOUNTS=["admin@example.com"])
def test_branding_view_get(admin_client: Client) -> None:
    cast(Any, CorporateIdentity).objects.create(
        organization_name="Residencias El Parque",
        tax_id="J-98765432-1",
    )
    response: Any = admin_client.get(reverse("mailadmin:branding"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Residencias El Parque" in content
    assert "J-98765432-1" in content


@override_settings(MAIL_ADMIN_ACCOUNTS=["admin@example.com"])
def test_branding_view_post_valid(admin_client: Client) -> None:
    data = {
        "organization_name": "Condominio Central",
        "tagline": "Servicio de Correo Oficial",
        "tax_id": "J-11223344-5",
        "fiscal_address": "Av. Principal Torre A",
        "support_email": "soporte@condominio.com",
        "support_phone": "+58 412 1112233",
        "website_url": "https://condominio.com",
        "terms_url": "https://condominio.com/terminos",
        "privacy_url": "https://condominio.com/privacidad",
        "logo_light_url": "https://condominio.com/logo-light.png",
        "logo_dark_url": "https://condominio.com/logo-dark.png",
        "favicon_url": "https://condominio.com/favicon.ico",
    }
    response: Any = admin_client.post(reverse("mailadmin:branding"), data)
    assert response.status_code == 302

    identity = CorporateIdentity.get_solo()
    assert identity.organization_name == "Condominio Central"
    assert identity.tax_id == "J-11223344-5"
    assert identity.support_email == "soporte@condominio.com"


@override_settings(MAIL_ADMIN_ACCOUNTS=["admin@example.com"])
def test_branding_view_post_htmx(admin_client: Client) -> None:
    data = {
        "organization_name": "Corporación Alpha",
        "tagline": "Líderes en Tecnología",
        "tax_id": "J-55667788-9",
    }
    response: Any = admin_client.post(
        reverse("mailadmin:branding"),
        data,
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert response["HX-Trigger"] == "brandingUpdated"
    content = response.content.decode("utf-8")
    assert "Corporación Alpha" in content
