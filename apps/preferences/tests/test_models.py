"""Tests for per-account mail preferences."""

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError
from django.test import override_settings
from django.utils import translation

from apps.preferences.constants import Density, Layout, RemoteImages, Theme
from apps.preferences.models import MailPreference

pytestmark = pytest.mark.django_db


def make_preference(**overrides):
    data = {
        "account_key": "a" * 64,
        "email": "user@example.com",
    }
    data.update(overrides)
    return MailPreference(**data)


def test_defaults_come_from_settings():
    preference = make_preference()
    preference.full_clean()
    preference.save()

    assert preference.theme == Theme.SYSTEM
    assert preference.density == Density.COMPACT
    assert preference.layout == Layout.SIDE
    assert preference.remote_images == RemoteImages.ASK
    assert preference.notifications_enabled is True
    assert preference.notification_sound_enabled is True
    assert preference.use_threads is False
    assert preference.html_allowed is True
    assert preference.special_folders == {}
    assert preference.page_size == 50
    assert preference.language == "en"
    assert preference.timezone == "UTC"
    assert str(preference) == "user@example.com"


@override_settings(MAIL_DEFAULT_PAGE_SIZE=25, MAIL_MAX_PAGE_SIZE=100)
def test_page_size_default_and_max_follow_settings():
    preference = make_preference()
    preference.full_clean()
    assert preference.page_size == 25

    preference.page_size = 101
    with pytest.raises(ValidationError) as exc_info:
        preference.full_clean()
    assert "page_size" in exc_info.value.message_dict


def test_page_size_must_be_positive():
    preference = make_preference(page_size=0)

    with pytest.raises(ValidationError) as exc_info:
        preference.full_clean()
    assert "page_size" in exc_info.value.message_dict


def test_language_must_be_available():
    preference = make_preference(language="xx")

    with pytest.raises(ValidationError) as exc_info:
        preference.full_clean()
    assert "language" in exc_info.value.message_dict


def test_timezone_must_be_valid():
    preference = make_preference(timezone="Mars/Olympus_Mons")

    with pytest.raises(ValidationError) as exc_info:
        preference.full_clean()
    assert "timezone" in exc_info.value.message_dict


@pytest.mark.django_db(transaction=True)
def test_account_key_is_unique():
    make_preference().save()

    with pytest.raises(IntegrityError):
        make_preference(email="other@example.com").save()


def test_email_is_validated():
    preference = make_preference(email="not-an-email")

    with pytest.raises(ValidationError) as exc_info:
        preference.full_clean()
    assert "email" in exc_info.value.message_dict


def test_verbose_names_are_lazy_and_migrations_match_in_spanish():
    with translation.override("es"):
        call_command("makemigrations", check=True, dry_run=True)
