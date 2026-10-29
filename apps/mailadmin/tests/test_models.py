"""Tests for corporate identity models."""

from __future__ import annotations

from typing import Any, cast

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.mailadmin.models import CorporateIdentity

pytestmark = pytest.mark.django_db


def test_corporate_identity_singleton() -> None:
    identity1 = CorporateIdentity.get_solo()
    assert identity1.pk == 1
    assert identity1.organization_name == ""

    identity1_any = cast(Any, identity1)
    identity1_any.organization_name = "Condominio Los Rosales"
    identity1_any.tax_id = "J-12345678-9"
    identity1.save()

    identity2 = CorporateIdentity.get_solo()
    assert identity2.pk == 1
    assert identity2.organization_name == "Condominio Los Rosales"
    assert identity2.tax_id == "J-12345678-9"
    assert cast(Any, CorporateIdentity).objects.count() == 1


def test_corporate_identity_save_enforces_pk_1() -> None:
    identity = CorporateIdentity(organization_name="Test Enterprise")
    identity.save()
    assert identity.pk == 1
    assert str(identity) == "Test Enterprise"


def test_corporate_identity_get_solo_db_error_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from django.db import ProgrammingError

    def mock_get_or_create(*args: Any, **kwargs: Any) -> Any:
        raise ProgrammingError('relation "mailadmin_corporateidentity" does not exist')

    monkeypatch.setattr(cast(Any, CorporateIdentity).objects, "get_or_create", mock_get_or_create)
    identity = CorporateIdentity.get_solo()
    assert identity.pk == 1
    assert identity.organization_name == ""


def test_corporate_identity_logo_mutual_exclusivity() -> None:
    dummy_file = SimpleUploadedFile("logo.png", b"fake-image-bytes", content_type="image/png")
    identity = CorporateIdentity(
        organization_name="Test Org",
        logo_light_file=dummy_file,
        logo_light_url="https://example.com/logo.png",
    )
    with pytest.raises(ValidationError) as exc_info:
        identity.full_clean()
    assert "logo_light_file" in exc_info.value.message_dict
    assert "logo_light_url" in exc_info.value.message_dict


def test_corporate_identity_effective_urls() -> None:
    identity = CorporateIdentity(
        organization_name="Test Org",
        logo_light_url="https://example.com/light.png",
        favicon_url="https://example.com/favicon.ico",
    )
    assert identity.effective_logo_light_url == "https://example.com/light.png"
    assert identity.effective_logo_dark_url == ""
    assert identity.effective_favicon_url == "https://example.com/favicon.ico"

    dummy_file = SimpleUploadedFile("dark.png", b"fake-dark-bytes", content_type="image/png")
    cast(Any, identity).logo_dark_file = dummy_file
    identity.save()
    assert identity.effective_logo_dark_url.startswith("/media/branding/")
