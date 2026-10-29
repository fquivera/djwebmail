"""Tests for new email arrival detection and notification endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.constants import (
    SESSION_NOTIFICATION_SOUND_ENABLED_KEY,
    SESSION_NOTIFICATIONS_ENABLED_KEY,
)
from apps.accounts.services.account import MailAccount
from apps.accounts.services.imap import FetchedSummary
from apps.mail.constants import IMAP_INBOX
from apps.mail.services.mailbox import check_new_inbox_messages

pytestmark = pytest.mark.django_db


@pytest.fixture
def account() -> MailAccount:
    return MailAccount(
        email="test@example.com",
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
    account: MailAccount,
) -> Client:
    monkeypatch.setattr(
        "apps.accounts.middleware.load_mail_account",
        lambda request: account,
    )
    monkeypatch.setattr(
        "apps.accounts.middleware.activate_session_timezone",
        lambda request: None,
    )
    session = client.session
    session["mail_email"] = account.email
    session.save()
    return client


def make_summary(
    uid: int,
    subject: str = "Test Subject",
    sender: str = "Alice <alice@example.com>",
    flags: tuple[str, ...] = (),
) -> FetchedSummary:
    headers = (
        f"From: {sender}\r\nSubject: {subject}\r\nDate: Mon, 1 Jan 2026 12:00:00 +0000\r\n\r\n"
    ).encode()
    return FetchedSummary(
        uid=uid,
        headers=headers,
        flags=flags,
        size=1024,
        internaldate=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )


def test_check_new_inbox_messages_establishes_baseline_when_none():
    mock_imap = MagicMock()
    mock_imap.search.return_value = [10, 11, 12]

    highest_uid, new_msg = check_new_inbox_messages(mock_imap, last_known_uid=None)

    assert highest_uid == 12
    assert new_msg is None
    mock_imap.select.assert_called_once_with(IMAP_INBOX, readonly=True)


def test_check_new_inbox_messages_returns_none_when_no_new_messages():
    mock_imap = MagicMock()
    mock_imap.search.return_value = [10, 11, 12]

    highest_uid, new_msg = check_new_inbox_messages(mock_imap, last_known_uid=12)

    assert highest_uid == 12
    assert new_msg is None


def test_check_new_inbox_messages_detects_new_unread_message():
    mock_imap = MagicMock()
    # First search(["ALL"]) returns all uids
    # Second search(["UID", ...]) returns unread uids above last_known_uid
    mock_imap.search.side_effect = [
        [10, 11, 12, 13],  # ALL
        [13],  # UNSEEN above 12
    ]
    mock_imap.fetch_summaries.return_value = [
        make_summary(13, subject="Urgent Announcement", sender="Boss <boss@example.com>")
    ]

    highest_uid, new_msg = check_new_inbox_messages(mock_imap, last_known_uid=12)

    assert highest_uid == 13
    assert new_msg is not None
    assert new_msg.uid == 13
    assert new_msg.subject == "Urgent Announcement"
    assert new_msg.sender == "Boss <boss@example.com>"


def test_check_new_inbox_messages_advances_uid_when_new_messages_are_seen():
    mock_imap = MagicMock()
    mock_imap.search.side_effect = [
        [10, 11, 12, 13],  # ALL
        [],  # UNSEEN above 12 is empty
    ]

    highest_uid, new_msg = check_new_inbox_messages(mock_imap, last_known_uid=12)

    assert highest_uid == 13
    assert new_msg is None


def test_notifications_check_view_requires_login(client: Client):
    url = reverse("mail:check_notifications")
    response: Any = client.get(url)
    assert response.status_code == 302


def test_notifications_check_view_baseline_sets_session(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
):
    mock_imap = MagicMock()
    mock_imap.search.return_value = [100, 101]

    class FakeCtx:
        def __enter__(self):
            return mock_imap

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("apps.mail.views.get_mail_imap_service", lambda request: FakeCtx())

    url = reverse("mail:check_notifications")
    response: Any = logged_in_client.get(url)

    assert response.status_code == 204
    assert "HX-Trigger" not in response
    assert logged_in_client.session.get("mail_last_known_uid") == 101


def test_notifications_check_view_triggers_notification_when_new_mail_arrives(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
):
    session = logged_in_client.session
    session["mail_last_known_uid"] = 101
    session[SESSION_NOTIFICATIONS_ENABLED_KEY] = True
    session[SESSION_NOTIFICATION_SOUND_ENABLED_KEY] = True
    session.save()

    mock_imap = MagicMock()
    mock_imap.search.side_effect = [
        [100, 101, 102],
        [102],
    ]
    mock_imap.fetch_summaries.return_value = [
        make_summary(102, subject="Welcome aboard", sender="Support <support@example.com>")
    ]

    class FakeCtx:
        def __enter__(self):
            return mock_imap

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("apps.mail.views.get_mail_imap_service", lambda request: FakeCtx())

    url = reverse("mail:check_notifications")
    response: Any = logged_in_client.get(url)

    assert response.status_code == 204
    assert "HX-Trigger" in response
    triggers = json.loads(response["HX-Trigger"])
    assert "mail:new-message" in triggers
    msg_detail = triggers["mail:new-message"]
    assert msg_detail["uid"] == 102
    assert msg_detail["subject"] == "Welcome aboard"
    assert msg_detail["sender"] == "Support <support@example.com>"
    assert msg_detail["sound"] is True
    assert msg_detail["notify"] is True
    assert msg_detail["folder"] == "INBOX"
    assert "/mail/message/INBOX/102/" in msg_detail["url"]
    assert triggers.get("mail:inbox-updated") is True

    assert logged_in_client.session.get("mail_last_known_uid") == 102
