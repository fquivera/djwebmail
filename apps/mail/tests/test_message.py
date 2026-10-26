"""Tests for message fetching, sanitization, and part extraction."""

from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime
from typing import cast

from apps.accounts.services.imap import ImapService
from apps.mail.services.message import (
    get_message,
    get_part,
    has_remote_content,
    rewrite_images,
    sanitize_html,
)


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


def build_message_with_attachments() -> EmailMessage:
    message = EmailMessage()
    message["From"] = "Alice <alice@example.com>"
    message["To"] = "Bob <bob@example.com>"
    message["Subject"] = "With attachments"
    message["Date"] = format_datetime(datetime(2026, 10, 22, 10, 0, tzinfo=UTC))
    message.make_mixed()

    body = EmailMessage()
    body.set_content("<p>Body</p>", subtype="html")
    message.attach(body)

    pdf = EmailMessage()
    pdf.set_content(b"%PDF-1.4", maintype="application", subtype="pdf")
    pdf["Content-Disposition"] = 'attachment; filename="report.pdf"'
    message.attach(pdf)

    png = EmailMessage()
    png.set_content(b"\x89PNG", maintype="image", subtype="png")
    png["Content-Disposition"] = 'attachment; filename="photo.png"'
    message.attach(png)
    return message


def build_message_with_inline_image() -> EmailMessage:
    message = EmailMessage()
    message["From"] = "Alice <alice@example.com>"
    message["To"] = "Bob <bob@example.com>"
    message["Subject"] = "Inline image"
    message["Date"] = format_datetime(datetime(2026, 10, 22, 10, 0, tzinfo=UTC))
    message.make_mixed()

    body = EmailMessage()
    body.set_content('<img src="cid:logo123"><p>Body</p>', subtype="html")
    message.attach(body)

    inline = EmailMessage()
    inline.set_content(b"\x89PNG", maintype="image", subtype="png")
    inline["Content-ID"] = "<logo123>"
    inline["Content-Disposition"] = 'inline; filename="logo.png"'
    message.attach(inline)
    return message


def test_sanitize_html_removes_scripts_and_event_handlers() -> None:
    html = '<p onclick="evil()">Hi<script>alert(1)</script></p><img src="x" onerror="bad()">'

    cleaned = sanitize_html(html)

    assert "<script" not in cleaned
    assert "onclick" not in cleaned
    assert "onerror" not in cleaned


def test_sanitize_html_removes_javascript_urls() -> None:
    html = '<a href="javascript:alert(1)">click</a><a href="https://example.com">ok</a>'

    cleaned = sanitize_html(html)

    assert "javascript:" not in cleaned
    assert 'href="https://example.com"' in cleaned


def test_sanitize_html_hardens_external_links() -> None:
    cleaned = sanitize_html('<a href="https://example.com">ok</a>')

    assert 'rel="noopener noreferrer nofollow"' in cleaned
    assert 'target="_blank"' in cleaned


def test_sanitize_html_keeps_http_and_cid_images_strips_data() -> None:
    html = (
        '<img src="https://example.com/a.png">'
        '<img src="cid:logo123">'
        '<img src="data:image/png;base64,AAA">'
        '<img src="https://example.com/b.png" onerror="bad()">'
    )

    cleaned = sanitize_html(html)

    assert '<img src="https://example.com/a.png">' in cleaned
    assert '<img src="cid:logo123">' in cleaned
    assert "data:image" not in cleaned
    assert "onerror" not in cleaned


def _inline_url(part: str) -> str:
    return f"/mail/message/INBOX/7/inline/{part}/"


def test_rewrite_images_proxies_remote_when_allowed() -> None:
    html = '<img src="https://example.com/a.png">'

    out = rewrite_images(
        html,
        proxy_base="/mail/image-proxy/",
        inline_url=_inline_url,
        inline_cids={},
        allow_remote=True,
    )

    assert 'src="/mail/image-proxy/?u=https%3A%2F%2Fexample.com%2Fa.png"' in out


def test_rewrite_images_drops_remote_when_blocked() -> None:
    html = '<img src="https://example.com/a.png">'

    out = rewrite_images(
        html,
        proxy_base="/mail/image-proxy/",
        inline_url=_inline_url,
        inline_cids={},
        allow_remote=False,
    )

    assert out == ""


def test_rewrite_images_rewrites_cid_and_drops_unknown() -> None:
    html = '<img src="cid:logo123"><img src="cid:unknown"><img>'

    out = rewrite_images(
        html,
        proxy_base="/mail/image-proxy/",
        inline_url=_inline_url,
        inline_cids={"logo123": "2"},
        allow_remote=False,
    )

    assert 'src="/mail/message/INBOX/7/inline/2/"' in out
    assert "unknown" not in out
    assert "<img>" not in out


def test_has_remote_content_detects_remote_but_not_cid() -> None:
    assert has_remote_content('<img src="https://example.com/a.png">') is True
    assert has_remote_content('<img src="cid:logo123">') is False
    assert has_remote_content('<iframe src="x"></iframe>') is True
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


def test_get_message_keeps_sanitized_images_and_flags_remote() -> None:
    raw = build_message(html='<p>Hi</p><img src="https://example.com/a.png">')
    imap = FakeImap(raw)

    message = get_message(cast(ImapService, imap), "INBOX", 7)

    assert message.body_kind == "html"
    assert '<img src="https://example.com/a.png">' in message.body_html
    assert message.remote_content_blocked is True


def test_get_message_falls_back_to_plain_text() -> None:
    raw = build_message(plain="Line one\nLine two <script>")
    imap = FakeImap(raw)

    message = get_message(cast(ImapService, imap), "INBOX", 7)

    assert message.body_kind == "plain"
    assert "Line one<br>" in message.body_html
    assert "&lt;script&gt;" in message.body_html
    assert message.remote_content_blocked is False


def test_get_message_extracts_attachments() -> None:
    imap = FakeImap(build_message_with_attachments().as_bytes())

    detail = get_message(cast(ImapService, imap), "INBOX", 7)

    assert [(a.part, a.filename) for a in detail.attachments] == [
        ("2", "report.pdf"),
        ("3", "photo.png"),
    ]
    assert detail.attachments[0].content_type == "application/pdf"
    assert detail.attachments[0].size == len(b"%PDF-1.4")


def test_get_message_maps_inline_cids_and_excludes_them_from_attachments() -> None:
    imap = FakeImap(build_message_with_inline_image().as_bytes())

    detail = get_message(cast(ImapService, imap), "INBOX", 7)

    assert detail.inline_cids == {"logo123": "2"}
    assert detail.attachments == ()


def test_get_message_attachment_only_body() -> None:
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
    assert [(a.part, a.filename) for a in detail.attachments] == [("1", "part-1")]


def test_get_part_returns_part_bytes() -> None:
    imap = FakeImap(build_message_with_attachments().as_bytes())

    result = get_part(cast(ImapService, imap), "INBOX", 7, "2")

    assert result is not None
    content, content_type, filename, disposition = result
    assert content == b"%PDF-1.4"
    assert content_type == "application/pdf"
    assert filename == "report.pdf"
    assert disposition == "attachment"


def test_get_part_returns_none_for_missing_part() -> None:
    imap = FakeImap(build_message_with_attachments().as_bytes())

    assert get_part(cast(ImapService, imap), "INBOX", 7, "99") is None
