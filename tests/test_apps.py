"""Project wiring checks."""

import pytest
from django.apps import apps
from django.conf import settings


def test_uses_test_settings():
    assert settings.SETTINGS_MODULE == "config.settings.test"


@pytest.mark.parametrize("label", ["accounts", "mail", "compose", "preferences"])
def test_project_apps_are_installed(label):
    config = apps.get_app_config(label)

    assert config.name == f"apps.{label}"
