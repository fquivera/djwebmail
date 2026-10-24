"""Tests for the transient compose attachment store."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.compose.attachments import (
    clear_attachments,
    list_attachments,
    load_attachments,
    remove_attachment,
    save_upload,
)
from apps.compose.exceptions import (
    AttachmentLimitReachedError,
    AttachmentTooLargeError,
    EmptyAttachmentError,
)

SESSION = "session-attachments"


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def upload(name: str = "report.txt", content: bytes = b"hello", content_type: str = "text/plain"):
    return SimpleUploadedFile(name, content, content_type=content_type)


def test_save_upload_stores_metadata_and_content() -> None:
    ref = save_upload(SESSION, upload())

    assert ref.name == "report.txt"
    assert ref.content_type == "text/plain"
    assert ref.size == 5
    assert list_attachments(SESSION) == (ref,)

    loaded = load_attachments(SESSION, [ref.id])
    assert len(loaded) == 1
    assert loaded[0].name == "report.txt"
    assert loaded[0].content == b"hello"


def test_save_upload_sanitizes_filename_and_content_type() -> None:
    ref = save_upload(
        SESSION,
        upload(name="../../secret/report.txt", content_type="text/plain\r\nBcc: evil@example.com"),
    )

    assert ref.name == "report.txt"
    assert ref.content_type == "text/plain"


def test_save_upload_rejects_empty_file() -> None:
    with pytest.raises(EmptyAttachmentError):
        save_upload(SESSION, upload(content=b""))


@override_settings(MAIL_MAX_ATTACHMENT_BYTES=4)
def test_save_upload_rejects_oversized_file() -> None:
    with pytest.raises(AttachmentTooLargeError):
        save_upload(SESSION, upload(content=b"12345"))


@override_settings(MAIL_MAX_ATTACHMENTS=1)
def test_save_upload_rejects_too_many_files() -> None:
    save_upload(SESSION, upload())

    with pytest.raises(AttachmentLimitReachedError):
        save_upload(SESSION, upload(name="second.txt"))


@override_settings(MAIL_MAX_ATTACHMENTS_TOTAL_BYTES=8)
def test_save_upload_rejects_total_size_over_limit() -> None:
    save_upload(SESSION, upload(content=b"1234"))

    with pytest.raises(AttachmentLimitReachedError):
        save_upload(SESSION, upload(name="second.txt", content=b"12345"))


def test_remove_attachment_deletes_it() -> None:
    first = save_upload(SESSION, upload())
    second = save_upload(SESSION, upload(name="second.txt"))

    remove_attachment(SESSION, first.id)

    assert list_attachments(SESSION) == (second,)
    assert load_attachments(SESSION, [first.id]) == ()


def test_clear_attachments_deletes_everything() -> None:
    ref = save_upload(SESSION, upload())

    clear_attachments(SESSION)

    assert list_attachments(SESSION) == ()
    assert load_attachments(SESSION, [ref.id]) == ()


def test_attachments_are_scoped_to_the_session() -> None:
    ref = save_upload(SESSION, upload())

    assert list_attachments("another-session") == ()
    assert load_attachments("another-session", [ref.id]) == ()


def test_load_attachments_ignores_unknown_and_duplicate_ids() -> None:
    ref = save_upload(SESSION, upload())

    loaded = load_attachments(SESSION, [ref.id, ref.id, "missing"])

    assert len(loaded) == 1
