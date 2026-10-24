"""Message read model: fetch, sanitize, and expose one message for the viewer."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html import escape
from typing import cast
from urllib.parse import quote

import nh3

from apps.accounts.services.imap import ImapService
from apps.mail.constants import (
    IMAGE_PROXY_ALLOWED_SCHEMES,
    MESSAGE_FLAG_FLAGGED,
    MESSAGE_FLAG_SEEN,
)

# The viewer only renders a deliberately small subset of HTML. Scripts, styles,
# forms, and media are stripped before the value reaches a template, so it is
# safe to render with ``|safe`` after sanitization. ``<img>`` is kept so inline
# (cid:) images and remote images can be rewritten by :func:`rewrite_images`.
ALLOWED_TAGS = frozenset(
    {
        "p",
        "br",
        "hr",
        "a",
        "b",
        "strong",
        "i",
        "em",
        "u",
        "s",
        "del",
        "ins",
        "small",
        "sup",
        "sub",
        "code",
        "pre",
        "blockquote",
        "ul",
        "ol",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "span",
        "div",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "th",
        "td",
        "caption",
        "img",
    }
)
ALLOWED_ATTRIBUTES: dict[str, set[str]] = {
    "a": {"href", "title"},
    "img": {"src", "alt"},
    "ol": {"start"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
}
# ``cid`` is allowed so the sanitizer keeps inline image sources; they are
# rewritten to the same-origin inline endpoint before anything reaches a page.
ALLOWED_URL_SCHEMES = frozenset({"http", "https", "mailto", "cid"})
LINK_REL = "noopener noreferrer nofollow"

_IMAGE_SCHEME_PREFIXES = tuple(f"{scheme}://" for scheme in sorted(IMAGE_PROXY_ALLOWED_SCHEMES))

_REMOTE_IMG_RE = re.compile(r'<img\b[^>]*\bsrc=["\']?https?://', re.IGNORECASE)
_REMOTE_RESOURCE_RE = re.compile(
    r"<(?:iframe|video|audio|source|link)\b|background\s*=|url\(",
    re.IGNORECASE,
)
_ANCHOR_OPEN_RE = re.compile(r"<a\b([^>]*)>", re.IGNORECASE)
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_IMG_SRC_RE = re.compile(r'src="([^"]+)"', re.IGNORECASE)


@dataclass(frozen=True)
class Attachment:
    """One downloadable MIME part of a message."""

    part: str  # MIME part number, e.g. "2" or "2.1"
    filename: str
    content_type: str
    size: int
    disposition: str  # "attachment" or "inline"


@dataclass(frozen=True)
class MessageDetail:
    """Everything the viewer needs to render one message."""

    uid: int
    folder: str
    subject: str
    sender: str
    recipients: str
    cc: str
    date: datetime | None
    flags: tuple[str, ...]
    is_seen: bool
    is_flagged: bool
    body_kind: str  # "html" | "plain" | "empty"
    body_html: str  # sanitized, safe to render with ``|safe``
    attachments: tuple[Attachment, ...]
    inline_cids: Mapping[str, str]  # cid (lowercased, no <>) -> part number
    remote_content_blocked: bool


def get_message(imap: ImapService, folder: str, uid: int) -> MessageDetail:
    """Fetch one message with ``BODY.PEEK[]`` so opening never sets ``\\Seen``."""
    imap.select(folder, readonly=True)
    fetched = imap.fetch_message(uid, peek=True)

    try:
        message = cast(
            EmailMessage,
            BytesParser(policy=policy.default).parsebytes(fetched.raw),
        )
    except Exception:
        message = None

    body_kind, body_html, remote_content_blocked = _extract_body(message)
    attachments, inline_cids = _analyze_parts(message) if message else ((), {})

    return MessageDetail(
        uid=uid,
        folder=folder,
        subject=_header_text(message.get("Subject")) if message else "",
        sender=_header_text(message.get("From")) if message else "",
        recipients=_header_text(message.get("To")) if message else "",
        cc=_header_text(message.get("Cc")) if message else "",
        date=_parse_date(_header_text(message.get("Date")) if message else ""),
        flags=fetched.flags,
        is_seen=_has_flag(fetched.flags, MESSAGE_FLAG_SEEN),
        is_flagged=_has_flag(fetched.flags, MESSAGE_FLAG_FLAGGED),
        body_kind=body_kind,
        body_html=body_html,
        attachments=attachments,
        inline_cids=inline_cids,
        remote_content_blocked=remote_content_blocked,
    )


def get_part(
    imap: ImapService,
    folder: str,
    uid: int,
    part: str,
) -> tuple[bytes, str, str, str] | None:
    """Return ``(bytes, content_type, filename, disposition)`` for one part."""
    imap.select(folder, readonly=True)
    fetched = imap.fetch_message(uid, peek=True)
    try:
        message = cast(
            EmailMessage,
            BytesParser(policy=policy.default).parsebytes(fetched.raw),
        )
    except Exception:
        return None

    for number, email_part in _walk_parts(message):
        if number == part:
            raw = email_part.get_payload(decode=True)
            content = raw if isinstance(raw, bytes) else b""
            content_type = email_part.get_content_type() or "application/octet-stream"
            filename = email_part.get_filename() or f"part-{part}"
            disposition = (email_part.get_content_disposition() or "attachment").lower()
            return content, content_type, filename, disposition
    return None


def sanitize_html(html: str) -> str:
    """Strip unsafe markup and harden links; the result is safe to render."""
    cleaned = nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel=LINK_REL,
        attribute_filter=_image_src_filter,
    )
    return _ANCHOR_OPEN_RE.sub(
        lambda match: f'<a{match.group(1)} target="_blank">',
        cleaned,
    )


def rewrite_images(
    html: str,
    *,
    proxy_base: str,
    inline_url: Callable[[str], str],
    inline_cids: Mapping[str, str],
    allow_remote: bool,
) -> str:
    """Rewrite ``<img>`` sources and drop images that must not load.

    Inline ``cid:`` images become same-origin inline URLs; remote HTTP(S) images
    become proxy URLs only when ``allow_remote`` is true, otherwise the tag is
    removed. Anything else (``data:``, unknown cid) is removed.
    """

    def replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        src_match = _IMG_SRC_RE.search(tag)
        if src_match is None:
            return ""
        src = src_match.group(1)
        lower = src.lower()

        if lower.startswith("cid:"):
            cid = src[4:].strip().lower()
            part = inline_cids.get(cid)
            if part is None:
                return ""
            return _IMG_SRC_RE.sub(lambda m: f'src="{inline_url(part)}"', tag, count=1)

        if lower.startswith(_IMAGE_SCHEME_PREFIXES):
            if not allow_remote:
                return ""
            proxy = f"{proxy_base}?u={quote(src, safe='')}"
            return _IMG_SRC_RE.sub(lambda m: f'src="{proxy}"', tag, count=1)

        return ""

    return _IMG_TAG_RE.sub(replace, html)


def _image_src_filter(element: str, attribute: str, value: str) -> str | None:
    if element == "img" and attribute == "src":
        lowered = value.lower()
        if lowered.startswith("cid:") or lowered.startswith(_IMAGE_SCHEME_PREFIXES):
            return value
        return None
    return value


def has_remote_content(html: str) -> bool:
    """Return True when the raw HTML references remote content (not ``cid:``)."""
    return bool(_REMOTE_IMG_RE.search(html) or _REMOTE_RESOURCE_RE.search(html))


def _extract_body(message: EmailMessage | None) -> tuple[str, str, bool]:
    if message is None:
        return "empty", "", False

    html_part = _find_part(message, "text/html")
    if html_part is not None:
        raw_html = _decode_part(html_part)
        return "html", sanitize_html(raw_html), has_remote_content(raw_html)

    plain_part = _find_part(message, "text/plain")
    if plain_part is not None:
        return "plain", _plain_to_html(_decode_part(plain_part)), False

    return "empty", "", False


def _find_part(message: EmailMessage, content_type: str) -> EmailMessage | None:
    if message.is_multipart():
        for part in message.walk():
            email_part = cast(EmailMessage, part)
            if (
                email_part.get_content_type() == content_type
                and email_part.get_payload(decode=True) is not None
            ):
                return email_part
        return None
    if message.get_content_type() == content_type:
        return message
    return None


def _walk_parts(message: EmailMessage) -> Iterator[tuple[str, EmailMessage]]:
    """Yield ``(part_number, leaf_part)`` for every non-multipart part."""

    def walk(msg: EmailMessage, number: str) -> Iterator[tuple[str, EmailMessage]]:
        if msg.is_multipart():
            for index, subpart in enumerate(msg.iter_parts(), start=1):
                sub_number = f"{number}.{index}" if number else str(index)
                yield from walk(cast(EmailMessage, subpart), sub_number)
        else:
            yield number or "1", msg

    yield from walk(message, "")


def _analyze_parts(
    message: EmailMessage,
) -> tuple[tuple[Attachment, ...], dict[str, str]]:
    """Return ``(attachments, inline_cids)`` for a parsed message."""
    attachments: list[Attachment] = []
    inline_cids: dict[str, str] = {}

    for number, part in _walk_parts(message):
        content_type = part.get_content_type()
        disposition = (part.get_content_disposition() or "").lower()
        filename = part.get_filename() or ""
        cid = (part.get("Content-ID") or "").strip().strip("<>").lower()

        if cid:
            inline_cids[cid] = number
            continue

        if (
            content_type in ("text/plain", "text/html")
            and not filename
            and disposition != "attachment"
        ):
            continue

        attachments.append(
            Attachment(
                part=number,
                filename=filename or f"part-{number}",
                content_type=content_type or "application/octet-stream",
                size=_part_size(part),
                disposition="inline" if disposition == "inline" else "attachment",
            )
        )

    return tuple(attachments), inline_cids


def _part_size(part: EmailMessage) -> int:
    payload = part.get_payload(decode=True)
    return len(payload) if isinstance(payload, bytes) else 0


def _decode_part(part: EmailMessage) -> str:
    try:
        payload = part.get_content()
    except Exception:
        payload = None
    if isinstance(payload, str):
        return payload
    raw = part.get_payload(decode=True)
    if isinstance(raw, str):
        return raw
    if isinstance(raw, bytes):
        charset = part.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")
    return ""


def _plain_to_html(text: str) -> str:
    return escape(text).replace("\r\n", "\n").replace("\n", "<br>\n")


def _has_flag(flags: Sequence[str], expected: str) -> bool:
    normalized = expected.casefold()
    return any(flag.casefold() == normalized for flag in flags)


def _header_text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
