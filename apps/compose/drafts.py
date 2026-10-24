"""Transient compose drafts.

A draft is the text of the form as the user types it, kept in the server-side
cache under the session scope. It is not mail yet: nothing is written to IMAP
or PostgreSQL. Sending or emptying the form clears it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from apps.compose.constants import (
    DRAFT_CACHE_PREFIX,
    MAX_ADDRESS_FIELD_CHARS,
    MAX_DRAFT_BODY_CHARS,
    MAX_SUBJECT_LENGTH,
)


@dataclass(frozen=True)
class Draft:
    """The text fields restored when the compose page reopens."""

    to: str
    cc: str
    subject: str
    body: str

    def as_initial(self) -> dict[str, str]:
        return {
            "to": self.to,
            "cc": self.cc,
            "subject": self.subject,
            "body": self.body,
        }

    @property
    def is_empty(self) -> bool:
        return not any(part.strip() for part in (self.to, self.cc, self.subject, self.body))


def save_draft(
    session_key: str,
    *,
    to: str,
    cc: str,
    subject: str,
    body: str,
) -> None:
    """Store the current form text, clearing it when every field is blank."""
    draft = Draft(
        to=to[:MAX_ADDRESS_FIELD_CHARS],
        cc=cc[:MAX_ADDRESS_FIELD_CHARS],
        subject=subject[:MAX_SUBJECT_LENGTH],
        body=body[:MAX_DRAFT_BODY_CHARS],
    )
    if draft.is_empty:
        clear_draft(session_key)
        return
    cache.set(
        _draft_key(session_key),
        draft.as_initial(),
        timeout=settings.MAIL_COMPOSE_TTL_SECONDS,
    )


def load_draft(session_key: str) -> Draft | None:
    """Return the stored draft, or ``None`` when there is none."""
    value = cache.get(_draft_key(session_key))
    if not isinstance(value, dict):
        return None
    return Draft(
        to=str(value.get("to", "")),
        cc=str(value.get("cc", "")),
        subject=str(value.get("subject", "")),
        body=str(value.get("body", "")),
    )


def clear_draft(session_key: str) -> None:
    cache.delete(_draft_key(session_key))


def _draft_key(session_key: str) -> str:
    digest = hashlib.sha256(session_key.encode("utf-8")).hexdigest()
    return f"{DRAFT_CACHE_PREFIX}{digest}"
