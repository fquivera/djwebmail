"""Unit tests for RFC 7095 jCard serialization and parsing."""

from __future__ import annotations

import json

import pytest

from apps.contacts.jcard import ContactData, build_jcard, parse_jcard, parse_jcard_stream


def test_build_and_parse_jcard_roundtrip() -> None:
    source = ContactData(
        uid="12345678-1234-5678-1234-567812345678",
        full_name="Ada Lovelace",
        email="ADA@Example.org",
        phone="+44 20 7946 0999",
        organization="Analytical Engine Group",
        job_title="Chief Mathematician",
        category="Colleagues",
        notes="Pioneer of computer programming.",
    )

    jcard = build_jcard(source)

    assert jcard[0] == "vcard"
    properties = jcard[1]
    assert ["version", {}, "text", "4.0"] in properties
    assert ["fn", {}, "text", "Ada Lovelace"] in properties
    assert ["email", {"type": "internet"}, "text", "ada@example.org"] in properties

    parsed = parse_jcard(jcard)
    assert parsed.uid == "12345678-1234-5678-1234-567812345678"
    assert parsed.full_name == "Ada Lovelace"
    assert parsed.email == "ada@example.org"
    assert parsed.phone == "+44 20 7946 0999"
    assert parsed.organization == "Analytical Engine Group"
    assert parsed.job_title == "Chief Mathematician"
    assert parsed.category == "Colleagues"
    assert parsed.notes == "Pioneer of computer programming."


def test_parse_jcard_derives_name_from_email_when_fn_is_blank() -> None:
    jcard = [
        "vcard",
        [
            ["version", {}, "text", "4.0"],
            ["email", {}, "text", "grace.hopper@example.org"],
        ],
    ]

    parsed = parse_jcard(jcard)
    assert parsed.full_name == "grace.hopper"
    assert parsed.email == "grace.hopper@example.org"


def test_parse_jcard_rejects_invalid_component() -> None:
    with pytest.raises(ValueError, match="vcard"):
        parse_jcard(["not-vcard", []])


def test_parse_jcard_rejects_missing_version_4() -> None:
    with pytest.raises(ValueError, match="4.0"):
        parse_jcard(["vcard", [["email", {}, "text", "ada@example.org"]]])


def test_parse_jcard_stream_supports_single_and_array_payloads() -> None:
    single = build_jcard(ContactData(full_name="Ada Lovelace", email="ada@example.org"))
    second = build_jcard(ContactData(full_name="Alan Turing", email="alan@example.org"))

    parsed_single = parse_jcard_stream(json.dumps(single))
    assert len(parsed_single) == 1
    assert parsed_single[0].email == "ada@example.org"

    parsed_multi = parse_jcard_stream(json.dumps([single, second]))
    assert [item.email for item in parsed_multi] == ["ada@example.org", "alan@example.org"]
