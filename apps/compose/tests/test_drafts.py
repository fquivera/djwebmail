"""Tests for the transient compose draft store."""

from __future__ import annotations

import pytest
from django.core.cache import cache

from apps.compose.constants import MAX_DRAFT_BODY_CHARS
from apps.compose.drafts import clear_draft, load_draft, save_draft

SESSION = "session-drafts"


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_save_and_load_draft_round_trips() -> None:
    save_draft(
        SESSION,
        to="alice@example.com",
        cc="carol@example.com",
        bcc="bob@example.com",
        subject="Hello",
        body="Body text",
    )

    draft = load_draft(SESSION)

    assert draft is not None
    assert draft.as_initial() == {
        "to": "alice@example.com",
        "cc": "carol@example.com",
        "bcc": "bob@example.com",
        "subject": "Hello",
        "body": "Body text",
    }


def test_empty_draft_is_not_stored() -> None:
    assert load_draft(SESSION) is None

    save_draft(SESSION, to="", cc="", subject="  ", body="\n")

    assert load_draft(SESSION) is None


def test_saving_an_empty_draft_clears_the_previous_one() -> None:
    save_draft(SESSION, to="alice@example.com", cc="", subject="Hello", body="Body")

    save_draft(SESSION, to="", cc="", subject="", body="")

    assert load_draft(SESSION) is None


def test_draft_body_is_clamped() -> None:
    save_draft(
        SESSION,
        to="alice@example.com",
        cc="",
        subject="Hello",
        body="x" * (MAX_DRAFT_BODY_CHARS + 1),
    )

    draft = load_draft(SESSION)

    assert draft is not None
    assert len(draft.body) == MAX_DRAFT_BODY_CHARS


def test_clear_draft_removes_it() -> None:
    save_draft(SESSION, to="alice@example.com", cc="", subject="Hello", body="Body")

    clear_draft(SESSION)

    assert load_draft(SESSION) is None


def test_drafts_are_scoped_to_the_session() -> None:
    save_draft(SESSION, to="alice@example.com", cc="", subject="Hello", body="Body")

    assert load_draft("another-session") is None
