"""Tests for compose form validation."""

from __future__ import annotations

import pytest

from apps.compose.constants import MAX_RECIPIENTS
from apps.compose.forms import ComposeForm


def test_valid_form_normalizes_recipients() -> None:
    form = ComposeForm(
        data={
            "to": "Alice <alice@example.com>, bob@example.com",
            "cc": "carol@example.com",
            "subject": "Hello",
            "body": "Body text",
        }
    )

    assert form.is_valid()
    assert form.cleaned_data["to"] == ["alice@example.com", "bob@example.com"]
    assert form.cleaned_data["cc"] == ["carol@example.com"]


def test_to_is_required() -> None:
    form = ComposeForm(data={"to": "", "subject": "Hello"})

    assert not form.is_valid()
    assert form.errors
    assert "to" in form.errors


def test_invalid_address_is_rejected() -> None:
    form = ComposeForm(data={"to": "not-an-address", "subject": "Hello"})

    assert not form.is_valid()
    assert form.errors
    assert "to" in form.errors


def test_cc_is_optional() -> None:
    form = ComposeForm(data={"to": "alice@example.com"})

    assert form.is_valid()
    assert form.cleaned_data["cc"] == []


def test_subject_cannot_contain_line_breaks() -> None:
    form = ComposeForm(data={"to": "alice@example.com", "subject": "Hello\nBcc: eve@example.com"})

    assert not form.is_valid()
    assert form.errors
    assert "subject" in form.errors


def test_recipients_cannot_contain_line_breaks() -> None:
    form = ComposeForm(data={"to": "alice@example.com\nBcc: eve@example.com"})

    assert not form.is_valid()
    assert form.errors
    assert "to" in form.errors


def test_recipient_limit_is_enforced() -> None:
    addresses = ", ".join(f"user{index}@example.com" for index in range(MAX_RECIPIENTS + 1))
    form = ComposeForm(data={"to": addresses})

    assert not form.is_valid()
    assert form.errors
    assert "to" in form.errors


@pytest.mark.parametrize("subject", ["", "Re: topic"])
def test_subject_is_optional(subject: str) -> None:
    form = ComposeForm(data={"to": "alice@example.com", "subject": subject})

    assert form.is_valid()
