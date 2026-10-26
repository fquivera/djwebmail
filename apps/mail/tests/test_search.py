"""Tests for folder-scoped search filters and IMAP criteria."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast
from urllib.parse import parse_qs

import pytest
from django.utils import translation

from apps.accounts.exceptions import ImapProtocolError
from apps.accounts.services.imap import FetchedSummary, Folder, ImapService
from apps.mail.constants import FOLDER_FLAG_NOSELECT, SEARCH_SCOPE_ALL
from apps.mail.forms import MailSearchForm
from apps.mail.services.search import SearchFilters, search_messages


class FakeSearchImap:
    """ImapService double that records search calls and can reject UTF-8."""

    def __init__(self, uids: list[int], *, reject_utf8: bool = False) -> None:
        self.uids = uids
        self.reject_utf8 = reject_utf8
        self.selected: tuple[str, bool] | None = None
        self.searches: list[tuple[object, str | None]] = []

    def select(self, folder: str, *, readonly: bool = False) -> None:
        self.selected = (folder, readonly)

    def search(self, criteria: object, *, charset: str | None = "UTF-8") -> list[int]:
        self.searches.append((criteria, charset))
        if self.reject_utf8 and charset == "UTF-8":
            raise ImapProtocolError("charset not supported")
        return list(self.uids)

    def fetch_summaries(self, uids: list[int], **kwargs: object) -> list[FetchedSummary]:
        return [_summary(uid) for uid in uids]


class FakeGlobalImap:
    """ImapService double with several folders and per-folder messages."""

    def __init__(
        self,
        folders: dict[str, list[FetchedSummary]],
        *,
        unselectable: set[str] | None = None,
        reject_utf8: bool = False,
    ) -> None:
        self.folders = folders
        self.unselectable = unselectable or set()
        self.reject_utf8 = reject_utf8
        self.current: str | None = None
        self.selected: list[tuple[str, bool]] = []
        self.searches: list[tuple[str, object, str | None]] = []
        self.fetched: dict[str, list[int]] = {}

    def list_folders(self) -> list[Folder]:
        return [
            Folder(
                name=name,
                delimiter="/",
                flags=(FOLDER_FLAG_NOSELECT,) if name in self.unselectable else (),
            )
            for name in self.folders
        ]

    def select(self, folder: str, *, readonly: bool = False) -> None:
        self.current = folder
        self.selected.append((folder, readonly))

    def search(self, criteria: object, *, charset: str | None = "UTF-8") -> list[int]:
        assert self.current is not None
        self.searches.append((self.current, criteria, charset))
        if self.reject_utf8 and charset == "UTF-8":
            raise ImapProtocolError("charset not supported")
        return [summary.uid for summary in self.folders[self.current]]

    def fetch_summaries(self, uids: list[int], **kwargs: object) -> list[FetchedSummary]:
        assert self.current is not None
        self.fetched.setdefault(self.current, []).extend(uids)
        by_uid = {summary.uid: summary for summary in self.folders[self.current]}
        return [by_uid[uid] for uid in uids]


def _summary(uid: int, *, date: datetime | None = None) -> FetchedSummary:
    stamp = date or datetime(2026, 10, 22, 10, 0, tzinfo=UTC)
    return FetchedSummary(
        uid=uid,
        headers=(
            f"Subject: Message {uid}\r\n"
            "From: Alice <alice@example.com>\r\n"
            "To: Bob <bob@example.com>\r\n"
            f"Date: {stamp.strftime('%a, %d %b %Y %H:%M:%S +0000')}\r\n"
            "\r\n"
        ).encode(),
        flags=(),
        size=1,
        internaldate=stamp,
    )


def test_date_inputs_keep_iso_format_in_spanish() -> None:
    with translation.override("es"):
        form = MailSearchForm(initial={"folder": "INBOX", "date_from": date(2026, 10, 1)})

    assert 'value="2026-10-01"' in str(form["date_from"])


def test_scope_choices_are_translated_in_spanish() -> None:
    with translation.override("es"):
        form = MailSearchForm(initial={"folder": "INBOX"})
        rendered = str(form["scope"])

    assert "Esta carpeta" in rendered
    assert "Todas las carpetas" in rendered


def test_search_filters_translate_to_imap_criteria() -> None:
    filters = SearchFilters(
        folder="INBOX",
        q="factura",
        from_address="alice@example.com",
        to="bob@example.com",
        subject="octubre",
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
        unread=True,
    )

    assert filters.criteria() == [
        "TEXT",
        "factura",
        "FROM",
        "alice@example.com",
        "TO",
        "bob@example.com",
        "SUBJECT",
        "octubre",
        "SINCE",
        date(2026, 10, 1),
        "BEFORE",
        date(2026, 11, 1),
        "UNSEEN",
    ]


def test_search_filters_without_text_use_all() -> None:
    assert SearchFilters().criteria() == ["ALL"]
    assert SearchFilters().is_active is False


def test_search_filters_serialize_query_string() -> None:
    filters = SearchFilters(
        folder="INBOX",
        q="hola mundo",
        from_address="alice@example.com",
        unread=True,
        date_from=date(2026, 10, 1),
    )

    parsed = parse_qs(filters.query_string())

    assert parsed == {
        "folder": ["INBOX"],
        "q": ["hola mundo"],
        "from": ["alice@example.com"],
        "date_from": ["2026-10-01"],
        "unread": ["1"],
    }
    assert filters.is_active is True


def test_search_messages_paginates_and_keeps_query_string() -> None:
    imap = FakeSearchImap([1, 2, 3, 4, 5])
    filters = SearchFilters(folder="INBOX", q="hello")

    result = search_messages(
        cast(ImapService, imap),
        filters,
        page=1,
        page_size=2,
    )

    assert imap.selected == ("INBOX", True)
    assert imap.searches == [(["TEXT", "hello"], "UTF-8")]
    assert [message.uid for message in result.page.messages] == [5, 4]
    assert result.page.query_string == "folder=INBOX&q=hello"
    assert result.used_ascii_fallback is False


def test_search_messages_falls_back_to_ascii_when_utf8_is_rejected() -> None:
    imap = FakeSearchImap([1], reject_utf8=True)
    filters = SearchFilters(folder="INBOX", q="búsqueda", subject="día")

    result = search_messages(
        cast(ImapService, imap),
        filters,
        page=1,
        page_size=50,
    )

    assert len(imap.searches) == 2
    assert imap.searches[0] == (["TEXT", "búsqueda", "SUBJECT", "día"], "UTF-8")
    assert imap.searches[1] == (["TEXT", "busqueda", "SUBJECT", "dia"], None)
    assert result.used_ascii_fallback is True
    assert result.page.query_string == "folder=INBOX&q=b%C3%BAsqueda&subject=d%C3%ADa"


def test_global_search_merges_selectable_folders_by_date() -> None:
    imap = FakeGlobalImap(
        {
            "INBOX": [
                _summary(1, date=datetime(2026, 10, 20, 10, 0, tzinfo=UTC)),
                _summary(2, date=datetime(2026, 10, 24, 10, 0, tzinfo=UTC)),
            ],
            "Archive": [
                _summary(3, date=datetime(2026, 10, 23, 10, 0, tzinfo=UTC)),
                _summary(4, date=datetime(2026, 10, 22, 10, 0, tzinfo=UTC)),
            ],
            "Trash": [_summary(5)],
        },
        unselectable={"Trash"},
    )
    filters = SearchFilters(folder="INBOX", scope=SEARCH_SCOPE_ALL, q="hello")

    first = search_messages(cast(ImapService, imap), filters, page=1, page_size=2)
    second = search_messages(cast(ImapService, imap), filters, page=2, page_size=2)

    assert first.page.total == 4
    assert first.page.page_count == 2
    assert [(message.folder, message.uid) for message in first.page.messages] == [
        ("INBOX", 2),
        ("Archive", 3),
    ]
    assert [(message.folder, message.uid) for message in second.page.messages] == [
        ("Archive", 4),
        ("INBOX", 1),
    ]
    assert first.page.query_string == "folder=INBOX&scope=all&q=hello"
    assert [folder for folder, _ in imap.selected] == [
        "Archive",
        "INBOX",
        "Archive",
        "INBOX",
    ]
    assert imap.searches == [
        ("Archive", ["TEXT", "hello"], "UTF-8"),
        ("INBOX", ["TEXT", "hello"], "UTF-8"),
        ("Archive", ["TEXT", "hello"], "UTF-8"),
        ("INBOX", ["TEXT", "hello"], "UTF-8"),
    ]
    assert first.truncated is False


def test_global_search_caps_each_folder_and_reports_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("apps.mail.services.search.GLOBAL_SEARCH_PER_FOLDER_LIMIT", 2)
    imap = FakeGlobalImap(
        {
            "INBOX": [
                _summary(1, date=datetime(2026, 10, 20, 10, 0, tzinfo=UTC)),
                _summary(2, date=datetime(2026, 10, 21, 10, 0, tzinfo=UTC)),
                _summary(3, date=datetime(2026, 10, 22, 10, 0, tzinfo=UTC)),
            ]
        }
    )
    filters = SearchFilters(folder="INBOX", scope=SEARCH_SCOPE_ALL, q="hello")

    result = search_messages(cast(ImapService, imap), filters, page=1, page_size=10)

    assert result.truncated is True
    assert result.page.total == 2
    assert [message.uid for message in result.page.messages] == [3, 2]
    assert imap.fetched["INBOX"] == [2, 3]


def test_global_search_falls_back_by_requerying_every_folder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imap = FakeGlobalImap(
        {
            "INBOX": [_summary(1)],
            "Archive": [_summary(2)],
        },
        reject_utf8=True,
    )
    filters = SearchFilters(folder="INBOX", scope=SEARCH_SCOPE_ALL, q="búsqueda")

    result = search_messages(cast(ImapService, imap), filters, page=1, page_size=10)

    assert result.used_ascii_fallback is True
    assert [entry[2] for entry in imap.searches] == ["UTF-8", None, None]
    assert [entry[1] for entry in imap.searches[-2:]] == [
        ["TEXT", "busqueda"],
        ["TEXT", "busqueda"],
    ]
    assert result.page.query_string == "folder=INBOX&scope=all&q=b%C3%BAsqueda"
