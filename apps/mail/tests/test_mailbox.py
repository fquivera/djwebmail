"""Tests for the mail read model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from apps.accounts.services.imap import FetchedSummary, Folder, ImapService
from apps.mail.constants import FOLDER_FLAG_NOSELECT, IMAP_INBOX, MESSAGE_FLAG_SEEN
from apps.mail.services.mailbox import (
    build_folder_tree,
    delete_message,
    list_messages,
    move_message,
    set_message_flags,
)


class FakeImap:
    """Minimal ImapService double for read-model tests."""

    def __init__(self, uids: list[int], summaries: dict[int, FetchedSummary]) -> None:
        self.uids = uids
        self.summaries = summaries
        self.selected: tuple[str, bool] | None = None
        self.stored_flags: list[tuple[list[int], tuple[str, ...], tuple[str, ...]]] = []
        self.deleted: list[tuple[list[int], bool]] = []
        self.moved: list[tuple[list[int], str]] = []

    def select(self, folder: str, *, readonly: bool = False) -> None:
        self.selected = (folder, readonly)

    def search(self, criteria: object, *, charset: str = "UTF-8") -> list[int]:
        return list(self.uids)

    def fetch_summaries(self, uids: list[int], **kwargs: object) -> list[FetchedSummary]:
        return [self.summaries[uid] for uid in uids]

    def store_flags(
        self,
        uids: list[int],
        *,
        add: tuple[str, ...] = (),
        remove: tuple[str, ...] = (),
    ) -> None:
        self.stored_flags.append((list(uids), add, remove))

    def delete(self, uids: list[int], *, expunge: bool = False) -> None:
        self.deleted.append((list(uids), expunge))

    def move(self, uids: list[int], destination: str) -> None:
        self.moved.append((list(uids), destination))


def make_summary(uid: int, subject: str | None = None, **overrides: object) -> FetchedSummary:
    header_subject = subject if subject is not None else f"Message {uid}"
    headers = (
        f"Subject: {header_subject}\r\n"
        "From: Alice <alice@example.com>\r\n"
        "To: Bob <bob@example.com>\r\n"
        "Date: Thu, 22 Oct 2026 10:00:00 +0000\r\n"
        "\r\n"
    ).encode()
    values: dict[str, object] = {
        "uid": uid,
        "headers": headers,
        "flags": (),
        "size": uid * 100,
        "internaldate": datetime(2026, 10, 22, 10, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return FetchedSummary(**values)  # type: ignore[arg-type]


def test_build_folder_tree_nests_children_and_sorts() -> None:
    folders = [
        Folder(name="INBOX", delimiter="/", flags=("\\HasNoChildren",)),
        Folder(name="INBOX/Archive", delimiter="/", flags=("\\HasNoChildren",)),
        Folder(name="Archive", delimiter="/", flags=(FOLDER_FLAG_NOSELECT,)),
    ]

    tree = build_folder_tree(folders)

    assert [node.name for node in tree] == [IMAP_INBOX, "Archive"]
    assert tree[0].children[0].name == "INBOX/Archive"
    assert tree[0].children[0].label == "Archive"
    assert tree[0].selectable is True
    assert tree[1].selectable is False


def test_build_folder_tree_creates_synthetic_parents() -> None:
    folders = [
        Folder(name="INBOX/2026/October", delimiter="/", flags=("\\HasNoChildren",)),
    ]

    tree = build_folder_tree(folders)

    assert tree[0].name is None
    assert tree[0].label == "INBOX"
    assert tree[0].selectable is False
    assert tree[0].children[0].name is None
    assert tree[0].children[0].children[0].name == "INBOX/2026/October"


def test_list_messages_paginates_newest_first() -> None:
    uids = [1, 2, 3, 4, 5]
    imap = FakeImap(uids, {uid: make_summary(uid) for uid in uids})

    first = list_messages(cast(ImapService, imap), "INBOX", page=1, page_size=2)

    assert imap.selected == ("INBOX", True)
    assert first.total == 5
    assert first.page_count == 3
    assert [message.uid for message in first.messages] == [5, 4]
    assert first.has_previous is False
    assert first.has_next is True
    assert first.next_page == 2

    second = list_messages(cast(ImapService, imap), "INBOX", page=2, page_size=2)
    assert [message.uid for message in second.messages] == [3, 2]
    assert second.previous_page == 1
    assert second.next_page == 3

    last = list_messages(cast(ImapService, imap), "INBOX", page=99, page_size=2)
    assert last.page == 3
    assert [message.uid for message in last.messages] == [1]
    assert last.has_next is False
    assert last.next_page is None


def test_list_messages_clamps_page_zero() -> None:
    imap = FakeImap([1, 2, 3], {uid: make_summary(uid) for uid in (1, 2, 3)})

    page = list_messages(cast(ImapService, imap), "INBOX", page=0, page_size=2)

    assert page.page == 1
    assert [message.uid for message in page.messages] == [3, 2]


def test_list_messages_empty_folder() -> None:
    imap = FakeImap([], {})

    page = list_messages(cast(ImapService, imap), "INBOX", page=1, page_size=50)

    assert page.total == 0
    assert page.page_count == 1
    assert page.messages == ()
    assert page.has_previous is False
    assert page.has_next is False


def test_list_messages_parses_headers_flags_and_dates() -> None:
    summary = make_summary(
        9,
        subject="=?utf-8?b?SGVsbG8=?=",
        flags=("\\Seen", "\\Flagged"),
        size=42,
    )
    imap = FakeImap([9], {9: summary})

    page = list_messages(cast(ImapService, imap), "INBOX", page=1, page_size=50)
    message = page.messages[0]

    assert message.subject == "Hello"
    assert "alice@example.com" in message.sender
    assert "bob@example.com" in message.recipients
    assert message.size == 42
    assert message.is_seen is True
    assert message.is_flagged is True
    assert message.date is not None
    assert message.date.year == 2026


def test_list_messages_falls_back_to_internal_date() -> None:
    internaldate = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    summary = FetchedSummary(
        uid=1,
        headers=b"Subject: No date\r\n\r\n",
        flags=(),
        size=1,
        internaldate=internaldate,
    )
    imap = FakeImap([1], {1: summary})

    page = list_messages(cast(ImapService, imap), "INBOX", page=1, page_size=50)

    assert page.messages[0].date == internaldate


def test_set_message_flags_stores_flags_and_returns_summary() -> None:
    summary = make_summary(5, flags=("\\Flagged",))
    imap = FakeImap([5], {5: summary})

    updated = set_message_flags(
        cast(ImapService, imap),
        "INBOX",
        5,
        add=(MESSAGE_FLAG_SEEN,),
    )

    assert imap.selected == ("INBOX", False)
    assert imap.stored_flags == [([5], (MESSAGE_FLAG_SEEN,), ())]
    assert updated is not None
    assert updated.uid == 5


def test_delete_message_deletes_and_expunges() -> None:
    imap = FakeImap([5], {5: make_summary(5)})

    delete_message(cast(ImapService, imap), "INBOX", 5)

    assert imap.selected == ("INBOX", False)
    assert imap.deleted == [([5], True)]


def test_move_message_moves_to_destination() -> None:
    imap = FakeImap([5], {5: make_summary(5)})

    move_message(cast(ImapService, imap), "INBOX", 5, "Archive")

    assert imap.selected == ("INBOX", False)
    assert imap.moved == [([5], "Archive")]
