"""Message read model: fetch and sanitize a single message for the viewer."""

from __future__ import annotations

import re
from collections.abc import Sequence
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

# The viewer only renders a deliberately small subset of HTML. Everything else
# (script, style, forms, media, images) is stripped before the value reaches a
# template, so it is safe to render with ``|safe`` after sanitization.
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
    }
)
ALLOWED_ATTRIBUTES: dict[str, set[str]] = {
    "a": {"href", "title"},
    "ol": {"start"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
}
ALLOWED_URL_SCHEMES = frozenset({"http", "https", "mailto"})
LINK_REL = "noopener noreferrer nofollow"

# The "load images" action re-adds <img>, but only for plain HTTP(S) sources
# that the proxy will fetch. data:/cid: are dropped; the proxy never forwards
# them and there is no inline-part endpoint yet.
ALLOWED_TAGS_WITH_IMAGES = ALLOWED_TAGS | {"img"}
ALLOWED_ATTRIBUTES_WITH_IMAGES = {**ALLOWED_ATTRIBUTES, "img": {"src", "alt"}}

_IMAGE_SCHEME_PREFIXES = tuple(f"{scheme}://" for scheme in sorted(IMAGE_PROXY_ALLOWED_SCHEMES))

_REMOTE_RESOURCE_RE = re.compile(
    r"<(?:img|iframe|video|audio|source|link)\b|background\s*=|url\(",
    re.IGNORECASE,
)
_ANCHOR_OPEN_RE = re.compile(r"<a\b([^>]*)>", re.IGNORECASE)
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_IMG_SRC_RE = re.compile(r'src="([^"]+)"', re.IGNORECASE)


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
    body_html: str  # safe to render with ``|safe``
    remote_content_blocked: bool


def get_message(
    imap: ImapService,
    folder: str,
    uid: int,
    *,
    allow_images: bool = False,
) -> MessageDetail:
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

    body_kind, body_html, remote_content_blocked = _extract_body(message, allow_images=allow_images)

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
        remote_content_blocked=remote_content_blocked,
    )


def sanitize_html(html: str, *, allow_images: bool = False) -> str:
    """Strip unsafe markup and harden links; the result is safe to render."""
    tags = ALLOWED_TAGS_WITH_IMAGES if allow_images else ALLOWED_TAGS
    attributes = ALLOWED_ATTRIBUTES_WITH_IMAGES if allow_images else ALLOWED_ATTRIBUTES
    cleaned = nh3.clean(
        html,
        tags=tags,
        attributes=attributes,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel=LINK_REL,
        attribute_filter=_image_src_filter,
    )
    return _ANCHOR_OPEN_RE.sub(
        lambda match: f'<a{match.group(1)} target="_blank">',
        cleaned,
    )


def proxy_remote_images(html: str, proxy_base: str) -> str:
    """Rewrite ``<img src>`` to the proxy and drop images without an HTTP(S) src."""

    def replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        src_match = _IMG_SRC_RE.search(tag)
        if src_match is None:
            return ""
        src = src_match.group(1)
        if not src.startswith(_IMAGE_SCHEME_PREFIXES):
            return ""
        proxy = f"{proxy_base}?u={quote(src, safe='')}"
        return _IMG_SRC_RE.sub(lambda m: f'src="{proxy}"', tag, count=1)

    return _IMG_TAG_RE.sub(replace, html)


def _image_src_filter(element: str, attribute: str, value: str) -> str | None:
    if element == "img" and attribute == "src":
        return value if value.startswith(_IMAGE_SCHEME_PREFIXES) else None
    return value


def has_remote_content(html: str) -> bool:
    """Return True when the raw HTML references remote or embedded resources."""
    return bool(_REMOTE_RESOURCE_RE.search(html))


def _extract_body(
    message: EmailMessage | None,
    *,
    allow_images: bool = False,
) -> tuple[str, str, bool]:
    if message is None:
        return "empty", "", False

    html_part = _find_part(message, "text/html")
    if html_part is not None:
        raw_html = _decode_part(html_part)
        return (
            "html",
            sanitize_html(raw_html, allow_images=allow_images),
            has_remote_content(raw_html),
        )

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
