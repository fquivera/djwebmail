"""Transient attachment storage for the compose form.

Attachments live in the server-side cache under an opaque per-session scope,
never in the database and never in the browser session. They expire with
``MAIL_COMPOSE_TTL_SECONDS`` and are cleared after a successful send.
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import UploadedFile
from django.utils.text import get_valid_filename

from apps.compose.constants import ATTACHMENT_CACHE_PREFIX
from apps.compose.exceptions import (
    AttachmentLimitReachedError,
    AttachmentTooLargeError,
    EmptyAttachmentError,
)

DEFAULT_CONTENT_TYPE = "application/octet-stream"
MAX_FILENAME_LENGTH = 255
_CONTENT_TYPE_PATTERN = re.compile(r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$")


@dataclass(frozen=True)
class AttachmentRef:
    """Metadata for one stored attachment, safe to render."""

    id: str
    name: str
    content_type: str
    size: int


@dataclass(frozen=True)
class Attachment:
    """A stored attachment with its bytes, ready for message assembly."""

    id: str
    name: str
    content_type: str
    content: bytes

    @property
    def size(self) -> int:
        return len(self.content)


def save_upload(session_key: str, upload: UploadedFile) -> AttachmentRef:
    """Validate and store one uploaded file for this session."""
    size = int(getattr(upload, "size", 0) or 0)
    if size <= 0:
        raise EmptyAttachmentError("The uploaded file is empty")
    if size > settings.MAIL_MAX_ATTACHMENT_BYTES:
        raise AttachmentTooLargeError("The uploaded file is too large")

    index = _read_index(session_key)
    if len(index) >= settings.MAIL_MAX_ATTACHMENTS:
        raise AttachmentLimitReachedError("Too many attachments")

    content = upload.read()
    if not content:
        raise EmptyAttachmentError("The uploaded file is empty")
    if len(content) > settings.MAIL_MAX_ATTACHMENT_BYTES:
        raise AttachmentTooLargeError("The uploaded file is too large")
    if sum(int(item["size"]) for item in index) + len(content) > (
        settings.MAIL_MAX_ATTACHMENTS_TOTAL_BYTES
    ):
        raise AttachmentLimitReachedError("The attachments exceed the total size limit")

    attachment_id = uuid4().hex
    name = _safe_filename(upload.name or "")
    content_type = _safe_content_type(upload.content_type, name)
    cache.set(
        _item_key(session_key, attachment_id),
        {"name": name, "content_type": content_type, "content": content},
        timeout=settings.MAIL_COMPOSE_TTL_SECONDS,
    )
    index.append(
        {
            "id": attachment_id,
            "name": name,
            "content_type": content_type,
            "size": len(content),
        }
    )
    _write_index(session_key, index)
    return AttachmentRef(
        id=attachment_id,
        name=name,
        content_type=content_type,
        size=len(content),
    )


def list_attachments(session_key: str) -> tuple[AttachmentRef, ...]:
    """Return metadata for every attachment stored for this session."""
    return tuple(
        AttachmentRef(
            id=str(item["id"]),
            name=str(item["name"]),
            content_type=str(item["content_type"]),
            size=int(item["size"]),
        )
        for item in _read_index(session_key)
    )


def load_attachments(session_key: str, ids: list[str]) -> tuple[Attachment, ...]:
    """Load the requested attachments, ignoring unknown or expired ids."""
    if not ids:
        return ()
    index = {str(item["id"]): item for item in _read_index(session_key)}
    attachments: list[Attachment] = []
    seen: set[str] = set()
    for attachment_id in ids:
        if attachment_id in seen:
            continue
        seen.add(attachment_id)
        item = index.get(attachment_id)
        if item is None:
            continue
        stored = cache.get(_item_key(session_key, attachment_id))
        if not isinstance(stored, dict):
            continue
        content = stored.get("content")
        if not isinstance(content, bytes):
            continue
        attachments.append(
            Attachment(
                id=attachment_id,
                name=str(item["name"]),
                content_type=str(item["content_type"]),
                content=content,
            )
        )
    return tuple(attachments)


def remove_attachment(session_key: str, attachment_id: str) -> None:
    """Delete one attachment and drop it from the index."""
    index = [item for item in _read_index(session_key) if str(item["id"]) != attachment_id]
    cache.delete(_item_key(session_key, attachment_id))
    _write_index(session_key, index)


def clear_attachments(session_key: str) -> None:
    """Delete every attachment stored for this session."""
    for item in _read_index(session_key):
        cache.delete(_item_key(session_key, str(item["id"])))
    cache.delete(_index_key(session_key))


def _read_index(session_key: str) -> list[dict[str, Any]]:
    value = cache.get(_index_key(session_key))
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and "id" in item]


def _write_index(session_key: str, index: list[dict[str, Any]]) -> None:
    if not index:
        cache.delete(_index_key(session_key))
        return
    cache.set(_index_key(session_key), index, timeout=settings.MAIL_COMPOSE_TTL_SECONDS)


def _safe_filename(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    safe = get_valid_filename(base)[:MAX_FILENAME_LENGTH]
    return safe or "attachment"


def _safe_content_type(content_type: str | None, filename: str) -> str:
    candidate = (content_type or "").strip()
    if _CONTENT_TYPE_PATTERN.fullmatch(candidate):
        return candidate.lower()
    guessed, _encoding = mimetypes.guess_type(filename)
    if guessed and _CONTENT_TYPE_PATTERN.fullmatch(guessed):
        return guessed.lower()
    return DEFAULT_CONTENT_TYPE


def _scope(session_key: str) -> str:
    return hashlib.sha256(session_key.encode("utf-8")).hexdigest()


def _index_key(session_key: str) -> str:
    return f"{ATTACHMENT_CACHE_PREFIX}index:{_scope(session_key)}"


def _item_key(session_key: str, attachment_id: str) -> str:
    return f"{ATTACHMENT_CACHE_PREFIX}item:{_scope(session_key)}:{attachment_id}"
