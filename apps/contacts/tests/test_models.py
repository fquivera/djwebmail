"""Model and service tests for RFC 7095 jCard contacts."""

from __future__ import annotations

import json

import pytest
from django.core.exceptions import ValidationError

from apps.contacts.models import Contact
from apps.contacts.selectors import list_contact_suggestions, list_contacts
from apps.contacts.services import (
    delete_contact_for_account,
    export_jcard_for_account,
    import_jcard_for_account,
    save_contact_for_account,
)

pytestmark = pytest.mark.django_db


def test_save_contact_synchronizes_canonical_jcard() -> None:
    contact = Contact(
        full_name="Grace Hopper",
        primary_email="GRACE@Example.org",
        organization="US Navy",
        job_title="Rear Admiral",
        category="VIP",
    )

    saved = save_contact_for_account("acct-1", contact)

    assert saved.account_key == "acct-1"
    assert saved.primary_email == "grace@example.org"
    assert saved.formatted_address == "Grace Hopper <grace@example.org>"
    assert saved.jcard[0] == "vcard"
    assert '"Grace Hopper"' in saved.jcard_pretty


def test_import_and_export_jcard_for_account_upserts_by_email() -> None:
    payload = [
        [
            "vcard",
            [
                ["version", {}, "text", "4.0"],
                ["fn", {}, "text", "Ada Lovelace"],
                ["email", {"type": "internet"}, "text", "ada@example.org"],
                ["org", {}, "text", "Analytical Engine"],
            ],
        ],
        [
            "vcard",
            [
                ["version", {}, "text", "4.0"],
                ["fn", {}, "text", "Alan Turing"],
                ["email", {"type": "internet"}, "text", "alan@example.org"],
            ],
        ],
    ]

    created, updated = import_jcard_for_account("acct-1", json.dumps(payload))
    assert (created, updated) == (2, 0)

    # Re-importing updates existing email and keeps account isolation
    payload[0][1][1] = ["fn", {}, "text", "Augusta Ada King"]
    created_2, updated_2 = import_jcard_for_account("acct-1", json.dumps([payload[0]]))
    assert (created_2, updated_2) == (0, 1)

    contacts = list_contacts("acct-1")
    assert [c.full_name for c in contacts] == ["Alan Turing", "Augusta Ada King"]
    assert list_contact_suggestions("acct-1") == [
        "Alan Turing <alan@example.org>",
        "Augusta Ada King <ada@example.org>",
    ]

    exported = export_jcard_for_account("acct-1")
    assert len(exported) == 2
    assert exported[0][0] == "vcard"

    assert delete_contact_for_account("acct-1", contacts[0].pk) is True
    assert len(list_contacts("acct-1")) == 1


def test_save_contact_with_accented_name_does_not_rfc2047_encode_formatted_address() -> None:
    contact = Contact(
        full_name="=?utf-8?q?Francisco_Antonio_Quivera_Gonz=C3=A1lez?=",
        primary_email="fquivera@example.org",
    )

    saved = save_contact_for_account("acct-1", contact)

    assert saved.full_name == "Francisco Antonio Quivera González"
    assert saved.formatted_address == "Francisco Antonio Quivera González <fquivera@example.org>"
    assert "=?" not in saved.formatted_address


def test_import_jcard_rejects_malformed_json() -> None:
    with pytest.raises(ValidationError):
        import_jcard_for_account("acct-1", "{not-valid-json")
