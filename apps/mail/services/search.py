"""Folder-scoped and global IMAP search with validated filters."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from math import ceil
from typing import Any
from urllib.parse import urlencode

from apps.accounts.exceptions import ImapProtocolError
from apps.accounts.services.imap import Folder, ImapService
from apps.mail.constants import (
    FOLDER_FLAG_NOSELECT,
    GLOBAL_SEARCH_PER_FOLDER_LIMIT,
    IMAP_INBOX,
    SEARCH_SCOPE_ALL,
    SEARCH_SCOPE_FOLDER,
)
from apps.mail.services.mailbox import MessagePage, MessageSummary, list_messages, parse_summary


@dataclass(frozen=True)
class SearchFilters:
    """The validated filters sent by the search form."""

    folder: str = IMAP_INBOX
    scope: str = SEARCH_SCOPE_FOLDER
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
        scope = str(data.get("scope") or SEARCH_SCOPE_FOLDER)
        if scope not in (SEARCH_SCOPE_FOLDER, SEARCH_SCOPE_ALL):
            scope = SEARCH_SCOPE_FOLDER
        return cls(
            folder=str(folder),
            scope=scope,
            q=str(data.get("q") or ""),
            from_address=str(data.get("from_") or ""),
            to=str(data.get("to") or ""),
            subject=str(data.get("subject") or ""),
            date_from=data.get("date_from"),
            date_to=data.get("date_to"),
            unread=bool(data.get("unread")),
        )

    @property
    def is_global(self) -> bool:
        """Whether the search spans every selectable folder."""
        return self.scope == SEARCH_SCOPE_ALL

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
        if self.is_global:
            params["scope"] = SEARCH_SCOPE_ALL
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
    truncated: bool = False


def search_messages(
    imap: ImapService,
    filters: SearchFilters,
    *,
    page: int,
    page_size: int,
) -> SearchResult:
    """Search one folder or every selectable folder, retrying without UTF-8."""
    if filters.is_global:
        return _search_all_folders(imap, filters, page=page, page_size=page_size)

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


def _search_all_folders(
    imap: ImapService,
    filters: SearchFilters,
    *,
    page: int,
    page_size: int,
) -> SearchResult:
    """Search every selectable folder and merge the newest matches by date.

    IMAP has no cross-folder search. Each folder is queried independently and
    capped to its newest ``GLOBAL_SEARCH_PER_FOLDER_LIMIT`` matches, so one
    large folder cannot make the request unbounded. The merged page is stable
    because it is ordered by message date, then folder name, then UID.
    """
    if page_size < 1:
        raise ValueError("page_size must be positive")

    folders = _selectable_folder_names(imap)
    try:
        messages, truncated = _collect_global_messages(
            imap,
            folders,
            criteria=filters.criteria(),
            charset="UTF-8",
        )
    except ImapProtocolError:
        messages, truncated = _collect_global_messages(
            imap,
            folders,
            criteria=filters.ascii_fallback().criteria(),
            charset=None,
        )
        used_ascii_fallback = True
    else:
        used_ascii_fallback = False

    ordered = sorted(messages, key=_newest_first)
    total = len(ordered)
    page_count = max(1, ceil(total / page_size))
    current_page = min(max(1, page), page_count)
    start = (current_page - 1) * page_size
    selected = tuple(ordered[start : start + page_size])

    result = MessagePage(
        folder=filters.folder,
        page=current_page,
        page_size=page_size,
        total=total,
        page_count=page_count,
        messages=selected,
        has_previous=current_page > 1,
        has_next=current_page < page_count,
        previous_page=current_page - 1 if current_page > 1 else None,
        next_page=current_page + 1 if current_page < page_count else None,
        query_string=filters.query_string(),
    )
    return SearchResult(
        page=result,
        used_ascii_fallback=used_ascii_fallback,
        truncated=truncated,
    )


def _selectable_folder_names(imap: ImapService) -> tuple[str, ...]:
    """Return stable, unique names for folders that can be selected."""
    names: list[str] = []
    for folder in imap.list_folders():
        if not folder.name or not _is_selectable(folder):
            continue
        if folder.name not in names:
            names.append(folder.name)
    return tuple(sorted(names))


def _is_selectable(folder: Folder) -> bool:
    return not any(flag.casefold() == FOLDER_FLAG_NOSELECT.casefold() for flag in folder.flags)


def _collect_global_messages(
    imap: ImapService,
    folders: Sequence[str],
    *,
    criteria: Sequence[object],
    charset: str | None,
) -> tuple[list[MessageSummary], bool]:
    messages: list[MessageSummary] = []
    truncated = False
    for folder in folders:
        imap.select(folder, readonly=True)
        uids = sorted(imap.search(criteria, charset=charset) or [])
        if len(uids) > GLOBAL_SEARCH_PER_FOLDER_LIMIT:
            uids = uids[-GLOBAL_SEARCH_PER_FOLDER_LIMIT:]
            truncated = True
        if not uids:
            continue
        messages.extend(parse_summary(summary, folder) for summary in imap.fetch_summaries(uids))
    return messages, truncated


def _newest_first(message: MessageSummary) -> tuple[float, str, int]:
    """Sort newest first, then by folder and UID for a deterministic page."""
    timestamp = message.date.timestamp() if message.date else float("-inf")
    return (-timestamp, message.folder, message.uid)


def _ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")
