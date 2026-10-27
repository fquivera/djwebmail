"""Project wiring checks."""

import pytest
from django.apps import apps
from django.conf import settings


def test_uses_test_settings():
    assert settings.SETTINGS_MODULE == "config.settings.test"


@pytest.mark.parametrize("label", ["accounts", "mail", "compose", "contacts", "preferences"])
def test_project_apps_are_installed(label):
    config = apps.get_app_config(label)

    assert config.name == f"apps.{label}"


def test_tailwind_uses_the_standalone_pipeline():
    assert apps.get_app_config("theme").name == "theme"
    assert settings.TAILWIND_APP_NAME == "theme"
    assert settings.TAILWIND_USE_STANDALONE_BINARY is True
