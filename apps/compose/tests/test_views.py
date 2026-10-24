"""Tests for the compose, reply, forward, and send views."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.exceptions import ImapConnectionError, SmtpAuthError
from apps.accounts.services.account import MailAccount
from apps.mail.services.message import MessageDetail


class FakeImapContext:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, *exc: object) -> None:
        return None


class FakeSmtp:
    def __init__(self) -> None:
        self.sent: tuple[str, list[str], bytes] | None = None

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def send(self, sender: str, recipients: list[str], raw: bytes) -> None:
        self.sent = (sender, list(recipients), raw)


@pytest.fixture
def mail_account() -> MailAccount:
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
def logged_in_client(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    mail_account: MailAccount,
) -> Client:
    monkeypatch.setattr(
        "apps.accounts.middleware.load_mail_account",
        lambda request: mail_account,
    )
    monkeypatch.setattr(
        "apps.accounts.middleware.activate_session_language",
        lambda request: None,
    )
    return client


@pytest.fixture
def detail() -> MessageDetail:
    return MessageDetail(
        uid=7,
        folder="INBOX",
        subject="Original subject",
        sender="Alice <alice@example.com>",
        recipients="Bob <bob@example.com>",
        cc="",
        date=datetime(2026, 10, 22, 10, 0, tzinfo=UTC),
        flags=(),
        is_seen=False,
        is_flagged=False,
        body_kind="plain",
        body_html="<p>Original body</p>",
        attachments=(),
        inline_cids={},
        remote_content_blocked=False,
    )


def test_compose_requires_login(client: Client) -> None:
    response: Any = client.get(reverse("compose:new"))

    assert response.status_code == 302
    assert response["Location"] == f"{reverse('accounts:login')}?next=%2Fcompose%2F"


def test_compose_renders_empty_form(logged_in_client: Client) -> None:
    response: Any = logged_in_client.get(reverse("compose:new"))

    assert response.status_code == 200
    assert b'name="to"' in response.content
    assert b'name="body"' in response.content
    assert b"Send" in response.content


def test_compose_send_requires_login(client: Client) -> None:
    response: Any = client.post(reverse("compose:send"), {"to": "alice@example.com"})

    assert response.status_code == 302


def test_compose_send_invalid_form_returns_422(logged_in_client: Client) -> None:
    response: Any = logged_in_client.post(reverse("compose:send"), {"to": ""})

    assert response.status_code == 422
    assert b"Enter at least one recipient." in response.content


def test_compose_send_delivers_message(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smtp = FakeSmtp()
    monkeypatch.setattr("apps.compose.views.get_mail_smtp_service", lambda request: smtp)

    response: Any = logged_in_client.post(
        reverse("compose:send"),
        {
            "to": "Alice <alice@example.com>",
            "cc": "carol@example.com",
            "subject": "Hello",
            "body": "Body text",
        },
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("mail:index")
    assert smtp.sent is not None
    sender, recipients, raw = smtp.sent
    assert sender == "user@example.com"
    assert recipients == ["alice@example.com", "carol@example.com"]
    assert b"Subject: Hello" in raw
    assert b"Body text" in raw


def test_compose_send_maps_auth_error_to_503(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RejectingSmtp:
        def __enter__(self) -> RejectingSmtp:
            raise SmtpAuthError("rejected")

        def __exit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(
        "apps.compose.views.get_mail_smtp_service",
        lambda request: RejectingSmtp(),
    )

    response: Any = logged_in_client.post(
        reverse("compose:send"),
        {"to": "alice@example.com", "subject": "Hello", "body": "Body"},
    )

    assert response.status_code == 503
    assert b"rejected the stored credentials" in response.content


def test_compose_reply_prefills_sender(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
    detail: MessageDetail,
) -> None:
    monkeypatch.setattr(
        "apps.compose.views.get_mail_imap_service",
        lambda request: FakeImapContext(),
    )
    monkeypatch.setattr("apps.compose.views.get_message", lambda imap, folder, uid: detail)

    response: Any = logged_in_client.get(
        reverse("compose:reply", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 200
    assert b'value="alice@example.com"' in response.content
    assert b'value="Re: Original subject"' in response.content


def test_compose_forward_prefills_quoted_body(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
    detail: MessageDetail,
) -> None:
    monkeypatch.setattr(
        "apps.compose.views.get_mail_imap_service",
        lambda request: FakeImapContext(),
    )
    monkeypatch.setattr("apps.compose.views.get_message", lambda imap, folder, uid: detail)

    response: Any = logged_in_client.get(
        reverse("compose:forward", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 200
    assert b'value="Fwd: Original subject"' in response.content
    assert b"Forwarded message" in response.content
    assert b"Original body" in response.content


def test_compose_reply_imap_error_returns_503(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(imap: Any, folder: str, uid: int) -> None:
        raise ImapConnectionError("down")

    monkeypatch.setattr(
        "apps.compose.views.get_mail_imap_service",
        lambda request: FakeImapContext(),
    )
    monkeypatch.setattr("apps.compose.views.get_message", fail)

    response: Any = logged_in_client.get(
        reverse("compose:reply", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 503
    assert b"Unable to load the message" in response.content
