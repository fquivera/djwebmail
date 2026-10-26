"""Tests for message assembly and the compose service helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from apps.accounts.services.smtp import SmtpService
from apps.compose.attachments import Attachment
from apps.compose.services import (
    build_message,
    forward_initial,
    html_to_text,
    reply_initial,
    send_message,
)
from apps.mail.services.message import MessageDetail


class FakeSmtp:
    def __init__(self) -> None:
        self.sent: tuple[str, list[str], bytes] | None = None

    def send(self, sender: str, recipients: list[str], raw: bytes) -> None:
        self.sent = (sender, list(recipients), raw)


def make_detail(**overrides: Any) -> MessageDetail:
    values: dict[str, Any] = {
        "uid": 7,
        "folder": "INBOX",
        "subject": "Original subject",
        "sender": "Alice <alice@example.com>",
        "recipients": "Bob <bob@example.com>",
        "cc": "",
        "date": datetime(2026, 10, 22, 10, 0, tzinfo=UTC),
        "flags": (),
        "is_seen": False,
        "is_flagged": False,
        "body_kind": "plain",
        "body_html": "<p>Original body</p>",
        "attachments": (),
        "inline_cids": {},
        "remote_content_blocked": False,
    }
    values.update(overrides)
    return MessageDetail(**values)


def test_build_message_sets_headers_and_body() -> None:
    message = build_message(
        sender="user@example.com",
        to=["alice@example.com"],
        cc=["carol@example.com"],
        subject="Hello",
        body="Body text",
    )

    assert message["From"] == "user@example.com"
    assert message["To"] == "alice@example.com"
    assert message["Cc"] == "carol@example.com"
    assert message["Subject"] == "Hello"
    assert str(message["Message-ID"]).endswith("@example.com>")
    assert message["Date"]
    assert message.get_content() == "Body text\n"


def test_reply_initial_targets_sender_and_prefixes_subject() -> None:
    initial = reply_initial(make_detail())

    assert initial["to"] == "alice@example.com"
    assert initial["subject"] == "Re: Original subject"


def test_reply_initial_does_not_duplicate_prefix() -> None:
    initial = reply_initial(make_detail(subject="Re: Original subject"))

    assert initial["subject"] == "Re: Original subject"


def test_forward_initial_quotes_original_body() -> None:
    initial = forward_initial(make_detail())

    assert initial["subject"] == "Fwd: Original subject"
    assert "Forwarded message" in initial["body"]
    assert "Alice <alice@example.com>" in initial["body"]
    assert "Original body" in initial["body"]


def test_html_to_text_strips_tags_and_unescapes() -> None:
    assert html_to_text("<p>Hello&nbsp;<b>world</b></p>") == "Hello world"


def test_build_message_adds_attachments() -> None:
    attachment = Attachment(
        id="attachment-1",
        name="report.txt",
        content_type="text/plain",
        content=b"attachment body",
    )

    message = build_message(
        sender="user@example.com",
        to=["alice@example.com"],
        cc=[],
        subject="Hello",
        body="Body text",
        attachments=[attachment],
    )

    assert message.get_content_type() == "multipart/mixed"
    parts = list(message.iter_attachments())
    assert len(parts) == 1
    assert parts[0].get_filename() == "report.txt"
    assert parts[0].get_content_type() == "text/plain"
    assert parts[0].get_payload(decode=True) == b"attachment body"


def test_build_message_falls_back_for_invalid_content_type() -> None:
    attachment = Attachment(
        id="attachment-1",
        name="data.bin",
        content_type="not-a-content-type",
        content=b"\x00\x01",
    )

    message = build_message(
        sender="user@example.com",
        to=["alice@example.com"],
        cc=[],
        subject="Hello",
        body="Body text",
        attachments=[attachment],
    )

    part = next(message.iter_attachments())
    assert part.get_content_type() == "application/octet-stream"


def test_build_message_assembles_html_alternative_when_html_is_present() -> None:
    message = build_message(
        sender="user@example.com",
        to=["alice@example.com"],
        cc=[],
        bcc=["blind@example.com"],
        subject="HTML Test",
        body="<p>Hello <b>world</b></p>",
    )

    assert message.is_multipart()
    assert message.get_content_type() == "multipart/alternative"
    parts = list(message.iter_parts())
    assert len(parts) == 2
    assert parts[0].get_content_type() == "text/plain"
    assert "Hello world" in str(parts[0].get_content())
    assert parts[1].get_content_type() == "text/html"
    assert "<p>Hello <b>world</b></p>" in str(parts[1].get_content())
    # Bcc header must NOT appear in the message headers
    assert "Bcc" not in message


def test_send_message_uses_all_recipients() -> None:
    smtp = FakeSmtp()

    send_message(
        cast(SmtpService, smtp),
        sender="user@example.com",
        to=["alice@example.com"],
        cc=["carol@example.com"],
        bcc=["dave@example.com"],
        subject="Hello",
        body="Body",
    )

    assert smtp.sent is not None
    sender, recipients, raw = smtp.sent
    assert sender == "user@example.com"
    assert recipients == ["alice@example.com", "carol@example.com", "dave@example.com"]
    assert b"Subject: Hello" in raw
    assert b"Bcc:" not in raw
