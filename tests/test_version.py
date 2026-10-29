"""Tests for application version discovery and system info context processor."""

from __future__ import annotations

import datetime
from unittest.mock import patch

from django.test import RequestFactory

from apps.accounts.constants import SESSION_SERVER_ENGINE_KEY
from common.context_processors import system_info
from common.version import DEFAULT_APP_VERSION, get_djwebmail_version


def test_get_djwebmail_version_reads_pyproject() -> None:
    version = get_djwebmail_version()
    assert isinstance(version, str)
    assert len(version.split(".")) >= 3


def test_get_djwebmail_version_fallback_on_missing_file() -> None:
    get_djwebmail_version.cache_clear()
    try:
        with patch("pathlib.Path.is_file", return_value=False):
            assert get_djwebmail_version() == DEFAULT_APP_VERSION
    finally:
        get_djwebmail_version.cache_clear()


def test_system_info_context_processor_unauthenticated() -> None:
    factory = RequestFactory()
    request = factory.get("/")
    request.session = {}  # type: ignore[assignment]

    context = system_info(request)
    assert context["djwebmail_version"] == get_djwebmail_version()
    assert context["mail_server_engine"] == ""
    assert context["current_year"] == datetime.date.today().year


def test_system_info_context_processor_with_engine_in_session() -> None:
    factory = RequestFactory()
    request = factory.get("/")
    request.session = {SESSION_SERVER_ENGINE_KEY: "Dovecot 2.4.1"}  # type: ignore[assignment]

    context = system_info(request)
    assert context["djwebmail_version"] == get_djwebmail_version()
    assert context["mail_server_engine"] == "Dovecot 2.4.1"
    assert context["current_year"] == datetime.date.today().year
