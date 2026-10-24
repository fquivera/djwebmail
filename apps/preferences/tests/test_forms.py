"""Tests for the preferences form."""

from __future__ import annotations

from typing import Any, cast

import pytest

from apps.preferences.constants import Density, Theme
from apps.preferences.forms import MailPreferenceForm, timezone_choices
from apps.preferences.models import MailPreference

pytestmark = pytest.mark.django_db


def make_preference() -> MailPreference:
    return cast(Any, MailPreference).objects.create(
        account_key="a" * 64,
        email="user@example.com",
        language="en",
        timezone="UTC",
    )


def test_timezone_choices_include_utc() -> None:
    assert ("UTC", "UTC") in timezone_choices()


def test_form_renders_language_and_timezone_choices() -> None:
    form = MailPreferenceForm(
        instance=MailPreference(language="es", timezone="Europe/Madrid"),
    )

    language_html = str(form["language"])
    timezone_html = str(form["timezone"])

    assert 'value="en"' in language_html
    assert 'value="es" selected' in language_html
    assert 'value="Europe/Madrid" selected' in timezone_html
    assert 'value="UTC"' in timezone_html


def test_valid_form_updates_preference() -> None:
    preference = make_preference()
    form = MailPreferenceForm(
        data={
            "language": "es",
            "timezone": "Europe/Madrid",
            "theme": Theme.DARK,
            "density": Density.COMFORTABLE,
            "page_size": "25",
        },
        instance=preference,
    )

    assert form.is_valid(), form.errors
    saved = form.save()

    assert saved.language == "es"
    assert saved.timezone == "Europe/Madrid"
    assert saved.theme == Theme.DARK
    assert saved.density == Density.COMFORTABLE
    assert saved.page_size == 25


@pytest.mark.parametrize("page_size", ["0", "201"])
def test_page_size_outside_settings_range_is_rejected(page_size: str) -> None:
    form = MailPreferenceForm(
        data={
            "language": "en",
            "timezone": "UTC",
            "theme": Theme.SYSTEM,
            "density": Density.COMPACT,
            "page_size": page_size,
        },
        instance=make_preference(),
    )

    assert not form.is_valid()
    errors = form.errors
    assert errors is not None
    assert "page_size" in errors


def test_unknown_language_is_rejected() -> None:
    form = MailPreferenceForm(
        data={
            "language": "xx",
            "timezone": "UTC",
            "theme": Theme.SYSTEM,
            "density": Density.COMPACT,
            "page_size": "50",
        },
        instance=make_preference(),
    )

    assert not form.is_valid()
    errors = form.errors
    assert errors is not None
    assert "language" in errors


def test_unknown_timezone_is_rejected() -> None:
    form = MailPreferenceForm(
        data={
            "language": "en",
            "timezone": "Mars/Olympus_Mons",
            "theme": Theme.SYSTEM,
            "density": Density.COMPACT,
            "page_size": "50",
        },
        instance=make_preference(),
    )

    assert not form.is_valid()
    errors = form.errors
    assert errors is not None
    assert "timezone" in errors
