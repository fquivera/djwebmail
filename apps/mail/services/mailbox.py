"""Mailbox read model: folder tree and paginated message summaries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import policy
from email.parser import BytesHeaderParser
from email.utils import parsedate_to_datetime
from math import ceil

from django.utils.translation import gettext as _

from apps.accounts.services.imap import FetchedSummary, Folder, ImapService
from apps.mail.constants import (
    DEFAULT_IMAP_DELIMITER,
    FOLDER_FLAG_NOSELECT,
    FOLDER_NAME_MAX_LENGTH,
    IMAP_INBOX,
    MESSAGE_FLAG_FLAGGED,
    MESSAGE_FLAG_SEEN,
)


@dataclass(frozen=True)
class FolderNode:
    """One node in the folder tree returned by IMAP LIST."""

    name: str | None
    label: str
    selectable: bool
    children: tuple[FolderNode, ...] = ()


@dataclass(frozen=True)
class MessageSummary:
    """The metadata needed to render one row in the message list."""

    uid: int
    subject: str
    sender: str
    recipients: str
    date: datetime | None
    flags: tuple[str, ...]
    size: int
    is_seen: bool
    is_flagged: bool
    folder: str = ""


@dataclass(frozen=True)
class MessagePage:
    """One page of message summaries plus pagination metadata."""

    folder: str
    page: int
    page_size: int
    total: int
    page_count: int
    messages: tuple[MessageSummary, ...]
    has_previous: bool
    has_next: bool
    previous_page: int | None
    next_page: int | None
    query_string: str = ""


@dataclass
class _MutableFolder:
    name: str | None = None
    label: str = ""
    selectable: bool = False
    children: dict[str, _MutableFolder] = field(default_factory=dict)


def build_folder_tree(folders: Sequence[Folder]) -> tuple[FolderNode, ...]:
    """Turn flat IMAP folder names into a stable tree using the IMAP delimiter."""
    if not folders:
        return ()

    delimiters = [folder.delimiter for folder in folders if folder.delimiter]
    default_delimiter = max(set(delimiters), key=delimiters.count) if delimiters else ""
    root = _MutableFolder()

    for folder in folders:
        if not folder.name:
            continue
        delimiter = folder.delimiter or default_delimiter
        parts = folder.name.split(delimiter) if delimiter else [folder.name]
        node = root
        for part in parts:
            node = node.children.setdefault(part, _MutableFolder(label=part))
        node.name = folder.name
        node.selectable = not _has_flag(folder.flags, FOLDER_FLAG_NOSELECT)

    return _freeze_children(root)


def list_folders(imap: ImapService) -> tuple[FolderNode, ...]:
    """Read the folder tree from an open IMAP service."""
    return build_folder_tree(imap.list_folders())


def create_user_folder(imap: ImapService, name: str, parent: str = "") -> str:
    """Validate and create a top-level or nested IMAP folder."""
    clean_name = name.strip()
    clean_parent = parent.strip()
    if not clean_name or len(clean_name) > FOLDER_NAME_MAX_LENGTH:
        raise ValueError("Invalid folder name length")
    if clean_name in {".", ".."} or any(ord(ch) < 32 or ord(ch) == 127 for ch in clean_name):
        raise ValueError("Invalid characters in folder name")

    folders = imap.list_folders() if hasattr(imap, "list_folders") else []
    delimiters = [folder.delimiter for folder in folders if folder.delimiter]
    delimiter = max(set(delimiters), key=delimiters.count) if delimiters else DEFAULT_IMAP_DELIMITER
    if delimiter and delimiter in clean_name:
        raise ValueError("Folder name cannot contain the hierarchy delimiter")

    existing_names = {folder.name for folder in folders if folder.name}
    if clean_parent:
        if existing_names and clean_parent not in existing_names:
            raise ValueError("Parent folder does not exist")
        full_name = f"{clean_parent}{delimiter}{clean_name}"
    else:
        full_name = clean_name

    if any(existing.casefold() == full_name.casefold() for existing in existing_names):
        raise ValueError("Folder already exists")

    imap.create_folder(full_name)
    return full_name


def list_messages(
    imap: ImapService,
    folder: str,
    *,
    page: int,
    page_size: int,
    criteria: Sequence[object] | str = "ALL",
    charset: str | None = "UTF-8",
    query_string: str = "",
) -> MessagePage:
    """Select one folder and return the requested page, newest messages first."""
    if page_size < 1:
        raise ValueError("page_size must be positive")

    imap.select(folder, readonly=True)
    uids = sorted(imap.search(criteria, charset=charset) or [])
    total = len(uids)
    page_count = max(1, ceil(total / page_size))
    current_page = min(max(1, page), page_count)

    if total == 0:
        return MessagePage(
            folder=folder,
            page=current_page,
            page_size=page_size,
            total=0,
            page_count=page_count,
            messages=(),
            has_previous=False,
            has_next=False,
            previous_page=None,
            next_page=None,
            query_string=query_string,
        )

    end = total - (current_page - 1) * page_size
    start = max(0, end - page_size)
    summaries = imap.fetch_summaries(uids[start:end])
    messages = tuple(parse_summary(summary, folder) for summary in reversed(summaries))

    return MessagePage(
        folder=folder,
        page=current_page,
        page_size=page_size,
        total=total,
        page_count=page_count,
        messages=messages,
        has_previous=current_page > 1,
        has_next=current_page < page_count,
        previous_page=current_page - 1 if current_page > 1 else None,
        next_page=current_page + 1 if current_page < page_count else None,
        query_string=query_string,
    )


def set_message_flags(
    imap: ImapService,
    folder: str,
    uid: int,
    *,
    add: Sequence[str] = (),
    remove: Sequence[str] = (),
) -> MessageSummary | None:
    """Add/remove flags on one message and return its refreshed summary."""
    imap.select(folder, readonly=False)
    imap.store_flags([uid], add=add, remove=remove)
    summaries = imap.fetch_summaries([uid])
    return parse_summary(summaries[0], folder) if summaries else None


def delete_message(imap: ImapService, folder: str, uid: int) -> None:
    """Mark one message deleted and expunge it."""
    imap.select(folder, readonly=False)
    imap.delete([uid], expunge=True)


def move_message(imap: ImapService, folder: str, uid: int, destination: str) -> None:
    """Move one message to another folder."""
    imap.select(folder, readonly=False)
    imap.move([uid], destination)


def batch_set_flags(
    imap: ImapService,
    folder: str,
    uids: Sequence[int],
    *,
    add: Sequence[str] = (),
    remove: Sequence[str] = (),
) -> None:
    """Add/remove flags on a batch of messages in ``folder``."""
    if not uids:
        return
    imap.select(folder, readonly=False)
    imap.store_flags(uids, add=add, remove=remove)


def batch_delete_messages(
    imap: ImapService,
    folder: str,
    uids: Sequence[int],
) -> None:
    """Mark a batch of messages deleted and expunge them."""
    if not uids:
        return
    imap.select(folder, readonly=False)
    imap.delete(uids, expunge=True)


def batch_move_messages(
    imap: ImapService,
    folder: str,
    uids: Sequence[int],
    destination: str,
) -> None:
    """Move a batch of messages to ``destination``."""
    if not uids:
        return
    imap.select(folder, readonly=False)
    imap.move(uids, destination)


def translate_folder_label(name: str) -> str:
    """Return a localized display label for standard IMAP folder names."""
    normalized = name.strip().casefold()
    if normalized == "inbox":
        return _("INBOX")
    if normalized in {"sent", "sent messages", "sent items"}:
        return _("Sent")
    if normalized in {"drafts", "draft"}:
        return _("Drafts")
    if normalized in {"trash", "deleted items", "deleted messages", "bin"}:
        return _("Trash")
    if normalized in {"spam", "junk", "junk e-mail"}:
        return _("Spam")
    if normalized in {"archive", "archives"}:
        return _("Archive")
    return name


def _freeze_children(node: _MutableFolder) -> tuple[FolderNode, ...]:
    children = sorted(
        node.children.values(),
        key=lambda child: (child.name != IMAP_INBOX, child.label.casefold()),
    )
    return tuple(
        FolderNode(
            name=child.name,
            label=translate_folder_label(child.label),
            selectable=child.selectable,
            children=_freeze_children(child),
        )
        for child in children
    )


def parse_summary(summary: FetchedSummary, folder: str = "") -> MessageSummary:
    """Turn one IMAP fetch result into the row read model."""
    try:
        headers = BytesHeaderParser(policy=policy.default).parsebytes(summary.headers)
    except Exception:
        headers = None

    subject = _header_text(headers.get("Subject")) if headers else ""
    sender = _header_text(headers.get("From")) if headers else ""
    recipients = _header_text(headers.get("To")) if headers else ""
    date = _parse_date(_header_text(headers.get("Date")) if headers else "") or _as_aware(
        summary.internaldate
    )

    return MessageSummary(
        uid=summary.uid,
        subject=subject,
        sender=sender,
        recipients=recipients,
        date=date,
        flags=summary.flags,
        size=summary.size,
        is_seen=_has_flag(summary.flags, MESSAGE_FLAG_SEEN),
        is_flagged=_has_flag(summary.flags, MESSAGE_FLAG_FLAGGED),
        folder=folder,
    )


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
    return _as_aware(parsed)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
