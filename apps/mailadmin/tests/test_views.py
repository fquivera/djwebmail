"""Tests for mailadmin views."""

from __future__ import annotations

from typing import Any, cast

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
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
    assert reverse("mail:index") in content


@override_settings(MAIL_ADMIN_ACCOUNTS=["admin@example.com"])
def test_header_branding_logic_variations(admin_client: Client) -> None:
    # 1. Default (no logo, no organization name) -> renders DjWebmail brand classes
    identity: Any = CorporateIdentity.get_solo()
    identity.organization_name = ""
    identity.logo_light_url = ""
    identity.save()

    resp_default: Any = admin_client.get(reverse("mailadmin:index"))
    content_default = resp_default.content.decode("utf-8")
    assert 'class="brand-dj"' in content_default
    assert 'class="brand-webmail"' in content_default

    # 2. Only organization name -> renders organization name, not DjWebmail wordmark in header
    identity.organization_name = "Acme Corp International"
    identity.save()

    resp_org: Any = admin_client.get(reverse("mailadmin:index"))
    content_org = resp_org.content.decode("utf-8")
    header_org = content_org.split("<main")[0]
    assert "Acme Corp International" in header_org
    assert 'class="brand-dj"' not in header_org

    # 3. Logo configured -> renders only the logo image in the brand link
    identity.logo_light_url = "https://example.com/logo.png"
    identity.save()

    resp_logo: Any = admin_client.get(reverse("mailadmin:index"))
    content_logo = resp_logo.content.decode("utf-8")
    header_logo = content_logo.split("<main")[0]
    assert 'src="https://example.com/logo.png"' in header_logo
    assert 'class="brand-dj"' not in header_logo


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


def test_admin_index_accessible_by_django_superuser(client: Client) -> None:
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    superuser = cast(Any, user_model).objects.create_superuser(
        username="superadmin",
        email="superadmin@example.com",
        password="secretpassword123",
    )
    client.force_login(superuser)
    response: Any = client.get(reverse("mailadmin:index"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "superadmin" in content
    assert reverse("mailadmin:branding") in content


@override_settings(MAIL_ADMIN_ACCOUNTS=["admin@example.com"])
def test_branding_view_post_file_upload(admin_client: Client) -> None:
    logo_file = SimpleUploadedFile("brand.png", b"test-logo-bytes", content_type="image/png")
    data = {
        "organization_name": "Empresa Archivo",
        "logo_light_file": logo_file,
    }
    response: Any = admin_client.post(reverse("mailadmin:branding"), data)
    assert response.status_code == 302
    identity = CorporateIdentity.get_solo()
    assert identity.organization_name == "Empresa Archivo"
    assert identity.logo_light_file is not None
    assert identity.effective_logo_light_url.startswith("/media/branding/")


@override_settings(MAIL_ADMIN_ACCOUNTS=["admin@example.com"])
def test_branding_view_post_conflict_file_and_url(admin_client: Client) -> None:
    logo_file = SimpleUploadedFile("brand.png", b"test-logo-bytes", content_type="image/png")
    data = {
        "organization_name": "Empresa Conflicto",
        "logo_light_file": logo_file,
        "logo_light_url": "https://example.com/logo.png",
    }
    response: Any = admin_client.post(
        reverse("mailadmin:branding"),
        data,
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 422
    content = response.content.decode("utf-8")
    assert "not both" in content or "no ambos" in content
