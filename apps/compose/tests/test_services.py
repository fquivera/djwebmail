"""Tests for message assembly and the compose service helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from apps.accounts.services.imap import Folder, ImapService
from apps.accounts.services.smtp import SmtpService
from apps.compose.attachments import Attachment
from apps.compose.services import (
    append_to_sent,
    apply_signature,
    build_message,
    extract_inline_images,
    forward_initial,
    html_to_text,
    reply_all_initial,
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


def test_build_message_formats_sender_display_name() -> None:
    message = build_message(
        sender="user@example.com",
        sender_name="Alice Smith",
        to=["bob@example.com"],
        cc=[],
        subject="Formatted From",
        body="Body text",
    )

    assert message["From"] == "Alice Smith <user@example.com>"
    assert str(message["Message-ID"]).endswith("@example.com>")


def test_reply_initial_targets_sender_and_prefixes_subject() -> None:
    initial = reply_initial(make_detail())

    assert initial["to"] == "alice@example.com"
    assert initial["subject"] == "Re: Original subject"


def test_reply_initial_does_not_duplicate_prefix() -> None:
    initial = reply_initial(make_detail(subject="Re: Original subject"))

    assert initial["subject"] == "Re: Original subject"


def test_reply_all_initial_includes_all_participants_except_self() -> None:
    detail = make_detail(
        sender="Alice <alice@example.com>",
        recipients="User <user@example.com>, Bob <bob@example.com>",
        cc="Carol <carol@example.com>, user@example.com",
    )

    initial = reply_all_initial(detail, account_email="user@example.com")

    assert initial["to"] == "alice@example.com, bob@example.com"
    assert initial["cc"] == "carol@example.com"
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


def test_apply_signature_adds_signature_block() -> None:
    initial = apply_signature({"to": "alice@example.com"}, "Best regards,\nUser")

    assert initial["to"] == "alice@example.com"
    assert "-- \nBest regards,\nUser" in initial["body"]


def test_apply_signature_adds_html_signature_block() -> None:
    html_sig = '<p><b>Alice</b><br><a href="https://example.com">Site</a></p>'
    initial = apply_signature({"to": "bob@example.com"}, html_sig)

    assert initial["to"] == "bob@example.com"
    assert 'class="mail-signature"' in initial["body"]
    assert "<b>Alice</b>" in initial["body"]
    assert "-- <br>" in initial["body"]


def test_append_to_sent_writes_to_sent_folder() -> None:
    class FakeImap:
        def __init__(self) -> None:
            self.appended: tuple[str, bytes, tuple[str, ...]] | None = None

        def list_folders(self) -> list[Folder]:
            return [
                Folder(name="INBOX", delimiter="/", flags=()),
                Folder(name="Sent", delimiter="/", flags=("\\Sent",)),
            ]

        def append(self, folder: str, raw: bytes, *, flags: tuple[str, ...] = ()) -> None:
            self.appended = (folder, raw, tuple(flags))

    imap = FakeImap()
    result = append_to_sent(cast(ImapService, imap), b"Subject: Test\r\n\r\nBody")

    assert result is True
    assert imap.appended == ("Sent", b"Subject: Test\r\n\r\nBody", ("\\Seen",))


def test_append_to_sent_creates_sent_folder_when_missing() -> None:
    class FakeImapWithoutSent:
        def __init__(self) -> None:
            self.created: list[str] = []
            self.appended: tuple[str, bytes, tuple[str, ...]] | None = None

        def list_folders(self) -> list[Folder]:
            return [Folder(name="INBOX", delimiter="/", flags=())]

        def create_folder(self, folder: str) -> None:
            self.created.append(folder)

        def append(self, folder: str, raw: bytes, *, flags: tuple[str, ...] = ()) -> None:
            self.appended = (folder, raw, tuple(flags))

    imap = FakeImapWithoutSent()
    result = append_to_sent(cast(ImapService, imap), b"Subject: Created\r\n\r\nBody")

    assert result is True
    assert imap.created == ["Sent"]
    assert imap.appended == ("Sent", b"Subject: Created\r\n\r\nBody", ("\\Seen",))


def test_extract_inline_images_converts_base64_to_cid() -> None:
    raw_html = '<p>Before</p><img src="data:image/png;base64,aGVsbG8=" alt="My Logo"><p>After</p>'
    transformed, parts = extract_inline_images(raw_html, domain="example.com")

    assert len(parts) == 1
    raw_data, maintype, subtype, cid = parts[0]
    assert raw_data == b"hello"
    assert maintype == "image"
    assert subtype == "png"
    assert f'src="cid:{cid}"' in transformed
    assert 'alt="My Logo"' in transformed
    assert "data:image/png;base64" not in transformed


def test_build_message_embeds_inline_cid_images() -> None:
    body = '<div>Hello world</div><img src="data:image/jpeg;base64,/9j/4AAQSkZJRg==" alt="Photo">'
    msg = build_message(
        sender="sender@example.com",
        to=["recipient@example.com"],
        cc=[],
        subject="Inline test",
        body=body,
    )

    as_str = msg.as_string()
    assert "Content-Type: multipart/related;" in as_str
    assert "Content-Type: image/jpeg" in as_str
    assert "Content-ID: <" in as_str
    assert "cid:" in as_str
