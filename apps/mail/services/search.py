"""Folder-scoped IMAP search with validated filters and ASCII fallback."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from apps.accounts.exceptions import ImapProtocolError
from apps.accounts.services.imap import ImapService
from apps.mail.constants import IMAP_INBOX
from apps.mail.services.mailbox import MessagePage, list_messages


@dataclass(frozen=True)
class SearchFilters:
    """The validated filters sent by the search form."""

    folder: str = IMAP_INBOX
    q: str = ""
    from_address: str = ""
    to: str = ""
    subject: str = ""
    date_from: date | None = None
    date_to: date | None = None
    unread: bool = False

    @classmethod
    def from_cleaned_data(cls, data: Mapping[str, Any]) -> SearchFilters:
        folder = data.get("folder") or IMAP_INBOX
        return cls(
            folder=str(folder),
            q=str(data.get("q") or ""),
            from_address=str(data.get("from_") or ""),
            to=str(data.get("to") or ""),
            subject=str(data.get("subject") or ""),
            date_from=data.get("date_from"),
            date_to=data.get("date_to"),
            unread=bool(data.get("unread")),
        )

    @property
    def is_active(self) -> bool:
        """Whether any filter changes the plain folder listing."""
        return bool(
            self.q
            or self.from_address
            or self.to
            or self.subject
            or self.date_from
            or self.date_to
            or self.unread
        )

    def criteria(self) -> list[object]:
        """Translate the filters to an IMAP SEARCH criteria list."""
        result: list[object] = []
        if self.q:
            result.extend(["TEXT", self.q])
        if self.from_address:
            result.extend(["FROM", self.from_address])
        if self.to:
            result.extend(["TO", self.to])
        if self.subject:
            result.extend(["SUBJECT", self.subject])
        if self.date_from:
            result.extend(["SINCE", self.date_from])
        if self.date_to:
            # BEFORE is exclusive; add one day so the selected end date is included.
            result.extend(["BEFORE", self.date_to + timedelta(days=1)])
        if self.unread:
            result.append("UNSEEN")
        return result or ["ALL"]

    def ascii_fallback(self) -> SearchFilters:
        """Return the filters with text fields folded to ASCII."""
        return replace(
            self,
            q=_ascii(self.q),
            from_address=_ascii(self.from_address),
            to=_ascii(self.to),
            subject=_ascii(self.subject),
        )

    def query_string(self) -> str:
        """Serialize the filters for pagination links."""
        params: dict[str, str] = {"folder": self.folder}
        if self.q:
            params["q"] = self.q
        if self.from_address:
            params["from"] = self.from_address
        if self.to:
            params["to"] = self.to
        if self.subject:
            params["subject"] = self.subject
        if self.date_from:
            params["date_from"] = self.date_from.isoformat()
        if self.date_to:
            params["date_to"] = self.date_to.isoformat()
        if self.unread:
            params["unread"] = "1"
        return urlencode(params)


@dataclass(frozen=True)
class SearchResult:
    """One page of search results plus the fallback state shown in the UI."""

    page: MessagePage
    used_ascii_fallback: bool = False


def search_messages(
    imap: ImapService,
    filters: SearchFilters,
    *,
    page: int,
    page_size: int,
) -> SearchResult:
    """Search the selected folder, retrying without UTF-8 when required."""
    try:
        result = list_messages(
            imap,
            filters.folder,
            page=page,
            page_size=page_size,
            criteria=filters.criteria(),
            query_string=filters.query_string(),
        )
    except ImapProtocolError:
        fallback = filters.ascii_fallback()
        result = list_messages(
            imap,
            filters.folder,
            page=page,
            page_size=page_size,
            criteria=fallback.criteria(),
            charset=None,
            query_string=filters.query_string(),
        )
        return SearchResult(page=result, used_ascii_fallback=True)
    return SearchResult(page=result)


def _ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")
