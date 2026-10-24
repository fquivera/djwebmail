"""Tests for the request-scoped SMTP service using a fake client."""

from __future__ import annotations

import smtplib
from collections.abc import Sequence
from typing import Any

import pytest

from apps.accounts.exceptions import SmtpAuthError, SmtpConnectionError, SmtpSendError
from apps.accounts.services.account import MailAccount
from apps.accounts.services.smtp import SmtpService


class FakeClient:
    """Minimal smtplib.SMTP double; no network and no implicit state."""

    def __init__(self) -> None:
        self.starttls_context: Any = None
        self.helo_count = 0
        self.logged_in: tuple[str, str] | None = None
        self.sent: tuple[str, list[str], bytes] | None = None
        self.quit_called = False
        self.close_called = False

    def starttls(self, context: Any = None) -> None:
        self.starttls_context = context

    def ehlo(self) -> None:
        self.helo_count += 1

    def login(self, username: str, password: str) -> None:
        self.logged_in = (username, password)

    def sendmail(self, sender: str, recipients: Sequence[str], raw: bytes) -> None:
        self.sent = (sender, list(recipients), raw)

    def quit(self) -> None:
        self.quit_called = True

    def close(self) -> None:
        self.close_called = True


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


def test_connect_starts_tls_and_logs_in(account: MailAccount) -> None:
    client = FakeClient()
    service = SmtpService(account, account.email, "secret", client_factory=lambda *a, **k: client)

    service.connect()

    assert client.starttls_context is not None
    assert client.helo_count == 1
    assert client.logged_in == (account.email, "secret")


def test_connect_without_password_skips_login(account: MailAccount) -> None:
    client = FakeClient()
    service = SmtpService(account, account.email, "", client_factory=lambda *a, **k: client)

    service.connect()

    assert client.logged_in is None


def test_connect_maps_authentication_failure(account: MailAccount) -> None:
    class RejectingClient(FakeClient):
        def login(self, username: str, password: str) -> None:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    service = SmtpService(
        account,
        account.email,
        "secret",
        client_factory=lambda *a, **k: RejectingClient(),
    )

    with pytest.raises(SmtpAuthError):
        service.connect()


def test_connect_maps_connection_failure(account: MailAccount) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("connection refused")

    service = SmtpService(account, account.email, "secret", client_factory=refuse)

    with pytest.raises(SmtpConnectionError):
        service.connect()


def test_send_delegates_to_smtp(account: MailAccount) -> None:
    client = FakeClient()
    service = SmtpService(account, account.email, "secret", client_factory=lambda *a, **k: client)
    with service as smtp:
        smtp.send(account.email, ["dest@example.com"], b"raw")

    assert client.sent == (account.email, ["dest@example.com"], b"raw")


def test_send_maps_rejection(account: MailAccount) -> None:
    class RejectingClient(FakeClient):
        def sendmail(self, sender: str, recipients: Sequence[str], raw: bytes) -> None:
            raise smtplib.SMTPRecipientsRefused({"dest@example.com": (550, b"no")})

    with SmtpService(
        account,
        account.email,
        "secret",
        client_factory=lambda *a, **k: RejectingClient(),
    ) as smtp:
        with pytest.raises(SmtpSendError):
            smtp.send(account.email, ["dest@example.com"], b"raw")


def test_close_logs_out(account: MailAccount) -> None:
    client = FakeClient()
    service = SmtpService(account, account.email, "secret", client_factory=lambda *a, **k: client)

    service.connect()
    service.close()

    assert client.quit_called is True
