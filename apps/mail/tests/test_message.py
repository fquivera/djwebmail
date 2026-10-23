"""Tests for message fetching and HTML sanitization."""

from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime
from typing import cast

from apps.accounts.services.imap import ImapService
from apps.mail.services.message import get_message, has_remote_content, sanitize_html


class FakeImap:
    """ImapService double that returns one raw message."""

    def __init__(self, raw: bytes, flags: tuple[str, ...] = ()) -> None:
        self.raw = raw
        self.flags = flags
        self.selected: tuple[str, bool] | None = None

    def select(self, folder: str, *, readonly: bool = False) -> None:
        self.selected = (folder, readonly)

    def fetch_message(self, uid: int, *, peek: bool = True) -> object:
        assert peek is True
        from apps.accounts.services.imap import FetchedMessage

        return FetchedMessage(uid=uid, raw=self.raw, flags=self.flags)


def build_message(html: str | None = None, plain: str | None = None) -> bytes:
    message = EmailMessage()
    message["From"] = "Alice <alice@example.com>"
    message["To"] = "Bob <bob@example.com>"
    message["Subject"] = "Hello"
    message["Date"] = format_datetime(datetime(2026, 10, 22, 10, 0, tzinfo=UTC))
    if html is not None:
        message.set_content(html, subtype="html")
    if plain is not None:
        message.add_alternative(plain, subtype="plain")
    return message.as_bytes()


def test_sanitize_html_removes_scripts_and_event_handlers() -> None:
    html = '<p onclick="evil()">Hi<script>alert(1)</script></p><img src="x" onerror="bad()">'

    cleaned = sanitize_html(html)

    assert "<script" not in cleaned
    assert "onclick" not in cleaned
    assert "onerror" not in cleaned
    assert "<img" not in cleaned


def test_sanitize_html_removes_javascript_urls() -> None:
    html = '<a href="javascript:alert(1)">click</a><a href="https://example.com">ok</a>'

    cleaned = sanitize_html(html)

    assert "javascript:" not in cleaned
    assert 'href="https://example.com"' in cleaned


def test_sanitize_html_hardens_external_links() -> None:
    cleaned = sanitize_html('<a href="https://example.com">ok</a>')

    assert 'rel="noopener noreferrer nofollow"' in cleaned
    assert 'target="_blank"' in cleaned


def test_has_remote_content_detects_resources() -> None:
    assert has_remote_content('<p>hi</p><img src="https://example.com/a.png">') is True
    assert has_remote_content('<p>hi</p><iframe src="x"></iframe>') is True
    assert has_remote_content('<p style="background: url(x)">hi</p>') is True
    assert has_remote_content("<p>just text</p>") is False


def test_get_message_prefers_html_and_sanitizes() -> None:
    raw = build_message(html="<p>Hello</p><script>bad()</script>", plain="Hello")
    imap = FakeImap(raw, flags=("\\Seen",))

    message = get_message(cast(ImapService, imap), "INBOX", 7)

    assert imap.selected == ("INBOX", True)
    assert message.uid == 7
    assert message.subject == "Hello"
    assert "alice@example.com" in message.sender
    assert message.body_kind == "html"
    assert "<script" not in message.body_html
    assert "Hello" in message.body_html
    assert message.is_seen is True
    assert message.remote_content_blocked is False


def test_get_message_blocks_and_flags_remote_images() -> None:
    raw = build_message(html='<p>Hi</p><img src="https://example.com/a.png">')
    imap = FakeImap(raw)

    message = get_message(cast(ImapService, imap), "INBOX", 7)

    assert message.body_kind == "html"
    assert "<img" not in message.body_html
    assert message.remote_content_blocked is True


def test_get_message_falls_back_to_plain_text() -> None:
    raw = build_message(plain="Line one\nLine two <script>")
    imap = FakeImap(raw)

    message = get_message(cast(ImapService, imap), "INBOX", 7)

    assert message.body_kind == "plain"
    assert "Line one<br>" in message.body_html
    assert "&lt;script&gt;" in message.body_html
    assert message.remote_content_blocked is False


def test_get_message_empty_body() -> None:
    message = EmailMessage()
    message["Subject"] = "Attachment only"
    message.make_mixed()
    attachment = EmailMessage()
    attachment.set_content(b"binary", maintype="application", subtype="octet-stream")
    message.attach(attachment)
    imap = FakeImap(message.as_bytes())

    detail = get_message(cast(ImapService, imap), "INBOX", 7)

    assert detail.body_kind == "empty"
    assert detail.body_html == ""
