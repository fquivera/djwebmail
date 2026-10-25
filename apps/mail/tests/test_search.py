"""Tests for folder-scoped search filters and IMAP criteria."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast
from urllib.parse import parse_qs

from django.utils import translation

from apps.accounts.exceptions import ImapProtocolError
from apps.accounts.services.imap import FetchedSummary, ImapService
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


def _summary(uid: int) -> FetchedSummary:
    return FetchedSummary(
        uid=uid,
        headers=(
            f"Subject: Message {uid}\r\n"
            "From: Alice <alice@example.com>\r\n"
            "To: Bob <bob@example.com>\r\n"
            "Date: Thu, 22 Oct 2026 10:00:00 +0000\r\n"
            "\r\n"
        ).encode(),
        flags=(),
        size=1,
        internaldate=datetime(2026, 10, 22, 10, 0, tzinfo=UTC),
    )


def test_date_inputs_keep_iso_format_in_spanish() -> None:
    with translation.override("es"):
        form = MailSearchForm(initial={"folder": "INBOX", "date_from": date(2026, 10, 1)})

    assert 'value="2026-10-01"' in str(form["date_from"])


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
