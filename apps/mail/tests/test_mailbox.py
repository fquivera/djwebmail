"""Tests for the mail read model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from django.utils import translation

from apps.accounts.services.imap import FetchedSummary, Folder, ImapService
from apps.mail.constants import FOLDER_FLAG_NOSELECT, IMAP_INBOX, MESSAGE_FLAG_SEEN
from apps.mail.services.mailbox import (
    archive_message,
    batch_archive_messages,
    batch_delete_messages,
    build_folder_tree,
    create_user_folder,
    delete_message,
    is_archive_folder,
    is_trash_folder,
    list_messages,
    move_message,
    resolve_archive_folder,
    resolve_trash_folder,
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


def test_delete_message_moves_to_trash_from_regular_folder() -> None:
    imap = FakeImap([5], {5: make_summary(5)})

    destination = delete_message(cast(ImapService, imap), "INBOX", 5)

    assert destination == "Trash"
    assert imap.selected == ("INBOX", False)
    assert imap.moved == [([5], "Trash")]
    assert imap.deleted == []


def test_delete_message_expunges_when_already_in_trash() -> None:
    imap = FakeImap([5], {5: make_summary(5)})

    destination = delete_message(cast(ImapService, imap), "Trash", 5)

    assert destination is None
    assert imap.selected == ("Trash", False)
    assert imap.deleted == [([5], True)]
    assert imap.moved == []


def test_batch_delete_messages_moves_or_expunges() -> None:
    imap = FakeImap([5, 6], {5: make_summary(5), 6: make_summary(6)})

    assert batch_delete_messages(cast(ImapService, imap), "INBOX", [5, 6]) == "Trash"
    assert imap.moved == [([5, 6], "Trash")]
    assert imap.deleted == []

    assert batch_delete_messages(cast(ImapService, imap), "Trash", [5, 6]) is None
    assert imap.deleted == [([5, 6], True)]


def test_move_message_moves_to_destination() -> None:
    imap = FakeImap([5], {5: make_summary(5)})

    move_message(cast(ImapService, imap), "INBOX", 5, "Archive")

    assert imap.selected == ("INBOX", False)
    assert imap.moved == [([5], "Archive")]


def test_build_folder_tree_translates_standard_folders_in_spanish() -> None:
    folders = [
        Folder(name="INBOX", delimiter="/", flags=("\\HasNoChildren",)),
        Folder(name="Sent", delimiter="/", flags=("\\HasNoChildren",)),
    ]

    with translation.override("es"):
        tree = build_folder_tree(folders)

    assert [node.name for node in tree] == ["INBOX", "Sent"]
    assert [node.label for node in tree] == ["Bandeja de entrada", "Enviados"]


def test_create_user_folder_supports_root_and_nested_folders() -> None:
    created: list[str] = []

    class FakeFolderImap:
        def list_folders(self) -> list[Folder]:
            return [
                Folder(name="INBOX", delimiter="/", flags=("\\HasNoChildren",)),
                Folder(name="Projects", delimiter="/", flags=("\\HasNoChildren",)),
            ]

        def create_folder(self, folder: str) -> None:
            created.append(folder)

    imap = cast(ImapService, FakeFolderImap())
    assert create_user_folder(imap, "Invoices") == "Invoices"
    assert create_user_folder(imap, "2026", parent="Projects") == "Projects/2026"
    assert created == ["Invoices", "Projects/2026"]


def test_resolve_and_archive_messages_creates_or_uses_archive_folder() -> None:
    created: list[str] = []
    moved: list[tuple[list[int], str]] = []

    class FakeArchiveImap:
        def __init__(self, folders: list[Folder]) -> None:
            self._folders = folders
            self.selected: tuple[str, bool] | None = None

        def list_folders(self) -> list[Folder]:
            return self._folders

        def create_folder(self, folder: str) -> None:
            created.append(folder)

        def select(self, folder: str, *, readonly: bool = True) -> None:
            self.selected = (folder, readonly)

        def move(self, uids: list[int], destination: str) -> None:
            moved.append((list(uids), destination))

    # Case 1: No Archive folder exists -> auto-creates "Archive"
    imap_missing = cast(
        ImapService,
        FakeArchiveImap([Folder(name="INBOX", delimiter="/", flags=("\\HasNoChildren",))]),
    )
    assert resolve_archive_folder(imap_missing) == "Archive"
    assert created == ["Archive"]

    # Case 2: RFC 6154 \Archive special-use flag present
    imap_flagged = cast(
        ImapService,
        FakeArchiveImap(
            [
                Folder(name="INBOX", delimiter="/", flags=("\\HasNoChildren",)),
                Folder(name="All Mail", delimiter="/", flags=("\\Archive",)),
            ]
        ),
    )
    assert archive_message(imap_flagged, "INBOX", 42) == "All Mail"
    assert batch_archive_messages(imap_flagged, "INBOX", [10, 11]) == "All Mail"
    assert moved == [([42], "All Mail"), ([10, 11], "All Mail")]
    assert is_archive_folder("Archive") is True
    assert is_archive_folder("INBOX/Archive") is True
    assert is_archive_folder("INBOX") is False


def test_trash_folder_resolution() -> None:
    created: list[str] = []
    moved: list[tuple[list[int], str]] = []
    deleted: list[tuple[list[int], bool]] = []

    class FakeTrashImap:
        def __init__(self, folders: list[Folder]) -> None:
            self._folders = folders
            self.selected: tuple[str, bool] | None = None

        def list_folders(self) -> list[Folder]:
            return self._folders

        def create_folder(self, folder: str) -> None:
            created.append(folder)

        def select(self, folder: str, *, readonly: bool = True) -> None:
            self.selected = (folder, readonly)

        def move(self, uids: list[int], destination: str) -> None:
            moved.append((list(uids), destination))

        def delete(self, uids: list[int], *, expunge: bool = False) -> None:
            deleted.append((list(uids), expunge))

    # Case 1: No Trash folder exists -> auto-creates "Trash"
    imap_missing = cast(
        ImapService,
        FakeTrashImap([Folder(name="INBOX", delimiter="/", flags=("\\HasNoChildren",))]),
    )
    assert resolve_trash_folder(imap_missing) == "Trash"
    assert created == ["Trash"]

    # Case 2: RFC 6154 \Trash special-use flag present
    imap_flagged = cast(
        ImapService,
        FakeTrashImap(
            [
                Folder(name="INBOX", delimiter="/", flags=("\\HasNoChildren",)),
                Folder(name="Corbeille", delimiter="/", flags=("\\Trash",)),
            ]
        ),
    )
    assert resolve_trash_folder(imap_flagged) == "Corbeille"
    assert delete_message(imap_flagged, "INBOX", 42) == "Corbeille"
    assert batch_delete_messages(imap_flagged, "INBOX", [10, 11]) == "Corbeille"
    assert moved == [([42], "Corbeille"), ([10, 11], "Corbeille")]

    # Case 3: Folder detection
    assert is_trash_folder("Trash") is True
    assert is_trash_folder("INBOX/Trash") is True
    assert is_trash_folder("Papelera") is True
    assert is_trash_folder("INBOX/Papelera") is True
    assert is_trash_folder("Deleted Messages") is True
    assert is_trash_folder("INBOX") is False
    assert is_trash_folder("Archive") is False
