"""View and integration tests for the RFC 7095 jCard contacts UI."""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.accounts.services.account import MailAccount
from apps.contacts.models import Contact
from apps.contacts.selectors import list_contacts
from apps.contacts.services import save_contact_for_account

pytestmark = pytest.mark.django_db


@pytest.fixture
def account() -> MailAccount:
    return MailAccount(
        email="user@example.com",
        domain="example.com",
        imap_host="imap.example.com",
        imap_port=993,  # hardcode-ok: test fixture
        imap_security="ssl",
        smtp_host="smtp.example.com",
        smtp_port=587,  # hardcode-ok: test fixture
        smtp_security="starttls",
    )


@pytest.fixture
def logged_in_client(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    account: MailAccount,
) -> Any:
    monkeypatch.setattr(
        "apps.accounts.middleware.load_mail_account",
        lambda request: account,
    )
    monkeypatch.setattr(
        "apps.accounts.middleware.activate_session_timezone",
        lambda request: None,
    )
    session = client.session
    session["mail_email"] = account.email
    session.save()
    return client


def test_contacts_index_requires_authentication(client: Any) -> None:
    response = client.get(reverse("contacts:index"))
    assert response.status_code == 302


def test_create_edit_and_delete_contact(logged_in_client: Any, account: MailAccount) -> None:
    response = logged_in_client.post(
        reverse("contacts:create"),
        {
            "full_name": "Ada Lovelace",
            "primary_email": "ada@example.org",
            "phone": "+44 20 7946 0999",
            "organization": "Analytical Engine",
            "job_title": "Mathematician",
            "category": "Engineering",
            "notes": "First programmer",
        },
    )
    assert response.status_code == 302

    contacts = list_contacts(account.account_key)
    assert len(contacts) == 1
    contact = contacts[0]
    assert contact.full_name == "Ada Lovelace"
    assert contact.jcard[0] == "vcard"

    # Duplicate email for the same account returns 422
    dup_response = logged_in_client.post(
        reverse("contacts:create"),
        {
            "full_name": "Another Ada",
            "primary_email": "ADA@example.org",
        },
    )
    assert dup_response.status_code == 422

    # Update existing contact
    update_response = logged_in_client.post(
        reverse("contacts:update", args=[contact.pk]),
        {
            "full_name": "Augusta Ada Lovelace",
            "primary_email": "ada@example.org",
            "phone": "+44 20 7946 0999",
            "organization": "Analytical Engine",
            "job_title": "Chief Mathematician",
            "category": "VIP",
            "notes": "Updated note",
        },
    )
    assert update_response.status_code == 302
    contact.refresh_from_db()
    assert contact.full_name == "Augusta Ada Lovelace"

    # Delete contact
    del_response = logged_in_client.post(reverse("contacts:delete", args=[contact.pk]))
    assert del_response.status_code == 302
    assert list_contacts(account.account_key) == []


def test_contacts_search_htmx_partial_and_sender_prefill(
    logged_in_client: Any,
    account: MailAccount,
) -> None:
    save_contact_for_account(
        account.account_key,
        Contact(full_name="Grace Hopper", primary_email="grace@example.org", category="Navy"),
    )
    save_contact_for_account(
        account.account_key,
        Contact(full_name="Alan Turing", primary_email="alan@example.org", category="Crypto"),
    )

    htmx_response = logged_in_client.get(
        reverse("contacts:index"),
        {"q": "Grace"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="contact-list-results",
    )
    assert htmx_response.status_code == 200
    body = htmx_response.content.decode("utf-8")
    assert "Grace Hopper" in body
    assert "Alan Turing" not in body

    prefill_response = logged_in_client.get(
        reverse("contacts:index"),
        {"sender": "Margaret Hamilton <margaret@example.org>"},
    )
    assert prefill_response.status_code == 200
    prefill_html = prefill_response.content.decode("utf-8")
    assert "Margaret Hamilton" in prefill_html
    assert "margaret@example.org" in prefill_html


def test_import_and_export_jcard_endpoints(
    logged_in_client: Any,
    account: MailAccount,
) -> None:
    jcard_doc = [
        "vcard",
        [
            ["version", {}, "text", "4.0"],
            ["fn", {}, "text", "Katherine Johnson"],
            ["email", {"type": "internet"}, "text", "katherine@example.org"],
        ],
    ]
    upload = SimpleUploadedFile(
        "contacts.jcard.json",
        json.dumps([jcard_doc]).encode("utf-8"),
        content_type="application/vcard+json",
    )
    import_response = logged_in_client.post(
        reverse("contacts:import_jcard"),
        {"jcard_file": upload},
    )
    assert import_response.status_code == 302

    export_response = logged_in_client.get(reverse("contacts:export_jcard"))
    assert export_response.status_code == 200
    assert "application/vcard+json" in export_response["Content-Type"]
    exported = json.loads(export_response.content.decode("utf-8"))
    assert len(exported) == 1
    assert exported[0][0] == "vcard"


def test_compose_includes_contact_suggestions_and_to_prefill(
    logged_in_client: Any,
    account: MailAccount,
) -> None:
    save_contact_for_account(
        account.account_key,
        Contact(
            full_name="Francisco Antonio Quivera González",
            primary_email="fquivera@example.org",
        ),
    )

    response = logged_in_client.get(
        reverse("compose:new"),
        {"to": "=?utf-8?q?Francisco_Antonio_Quivera_Gonz=C3=A1lez?= <fquivera@example.org>"},
    )
    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert 'id="contact-suggestions"' in html
    assert "Francisco Antonio Quivera González &lt;fquivera@example.org&gt;" in html
    assert "=?utf-8?" not in html


def test_contacts_page_renders_spanish_translations(logged_in_client: Any) -> None:
    response = logged_in_client.get(
        reverse("contacts:index"),
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 200
    assert "Contactos" in response.content.decode("utf-8")
