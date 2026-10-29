"""Tests for mail server diagnostics, probes, and health views."""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.services.account import MailAccount
from apps.mailadmin.diagnostics import (
    check_cache_service,
    check_database_service,
    check_imap_service,
    check_smtp_service,
    detect_mail_engine_from_banner,
    get_system_diagnostics,
    run_full_diagnostics,
)

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


@pytest.fixture(autouse=True)
def setup_admin_settings(settings: Any) -> None:
    settings.MAIL_ADMIN_ACCOUNTS = ["admin@example.com"]


def test_detect_mail_engine() -> None:
    assert detect_mail_engine_from_banner("* OK Dovecot ready.") == "Dovecot"
    assert detect_mail_engine_from_banner("220 mail.domain.com ESMTP Postfix") == "Postfix"
    assert detect_mail_engine_from_banner("* OK GreenMail ready") == "GreenMail (Test Server)"
    assert detect_mail_engine_from_banner("* OK Courier IMAP") == "Courier"
    assert detect_mail_engine_from_banner("Unknown server v1.0") == ""


def test_check_imap_unconfigured() -> None:
    with override_settings(MAIL_IMAP_HOST=""):
        res = check_imap_service()
        assert res.is_online is False
        assert res.error_message is not None


def test_check_imap_success_plain() -> None:
    fake_sock = MagicMock()
    fake_reader = io.StringIO("* OK [CAPABILITY IMAP4rev1 QUOTA IDLE] Dovecot ready.\r\n")
    fake_writer = io.StringIO()
    fake_sock.makefile.side_effect = lambda mode, **kwargs: (
        fake_reader if "r" in mode else fake_writer
    )

    with patch("socket.create_connection", return_value=fake_sock):
        res = check_imap_service(host="imap.example.test", port=143, security="none")

    assert res.is_online is True
    assert res.service_name == "IMAP"
    assert res.latency_ms is not None
    assert "QUOTA" in res.capabilities
    assert "IDLE" in res.capabilities
    assert res.engine_detected == "Dovecot"


def test_check_imap_connection_failure() -> None:
    with patch("socket.create_connection", side_effect=OSError("Connection refused")):
        res = check_imap_service(host="invalid.host.test", port=993, security="ssl")

    assert res.is_online is False
    assert "Connection refused" in str(res.error_message)


def test_check_smtp_unconfigured() -> None:
    with override_settings(MAIL_SMTP_HOST=""):
        res = check_smtp_service()
        assert res.is_online is False
        assert res.error_message is not None


def test_check_smtp_success() -> None:
    fake_sock = MagicMock()
    banner = "220 mail.example.test ESMTP Postfix\r\n250-STARTTLS\r\n250-SIZE 1024\r\n250 OK\r\n"
    fake_reader = io.StringIO(banner)
    fake_writer = io.StringIO()
    fake_sock.makefile.side_effect = lambda mode, **kwargs: (
        fake_reader if "r" in mode else fake_writer
    )

    with patch("socket.create_connection", return_value=fake_sock):
        res = check_smtp_service(host="smtp.example.test", port=587, security="none")

    assert res.is_online is True
    assert res.service_name == "SMTP"
    assert res.latency_ms is not None
    assert "STARTTLS" in res.capabilities
    assert "SIZE 1024" in res.capabilities
    assert res.engine_detected == "Postfix"


def test_check_database_and_cache_services() -> None:
    db_res = check_database_service()
    assert db_res.is_online is True
    assert db_res.latency_ms is not None
    assert db_res.latency_ms > 0

    cache_res = check_cache_service()
    assert cache_res.is_online is True
    assert cache_res.latency_ms is not None


def test_get_system_diagnostics() -> None:
    sys_diag = get_system_diagnostics()
    assert "python_version" in sys_diag
    assert "django_version" in sys_diag
    assert "djwebmail_version" in sys_diag
    assert "driver_class" in sys_diag


def test_run_full_diagnostics() -> None:
    with (
        patch("apps.mailadmin.diagnostics.check_imap_service") as mock_imap,
        patch("apps.mailadmin.diagnostics.check_smtp_service") as mock_smtp,
    ):
        mock_imap.return_value = check_database_service()  # online dummy
        mock_smtp.return_value = check_database_service()  # online dummy

        report = run_full_diagnostics()
        assert "imap" in report
        assert "smtp" in report
        assert "database" in report
        assert "cache" in report
        assert report["overall_status"] == "healthy"


class TestDiagnosticsView:
    """Test suite for the diagnostics dashboard view."""

    def test_permission_denied_for_regular_user(self, regular_client: Client) -> None:
        response: Any = regular_client.get(reverse("mailadmin:diagnostics"))
        assert response.status_code == 403

    def test_diagnostics_page_accessible_for_admin(self, admin_client: Client) -> None:
        response: Any = admin_client.get(reverse("mailadmin:diagnostics"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Diagnostics" in content
        assert "Service Health" in content
        assert "Primary Database" in content
        assert "Cache" in content

    def test_diagnostics_htmx_partial(self, admin_client: Client) -> None:
        response: Any = admin_client.get(
            reverse("mailadmin:diagnostics"),
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "IMAP Mail Service" in content
        assert "<!doctype html>" not in content
