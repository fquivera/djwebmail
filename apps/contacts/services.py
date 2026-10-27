"""Services for creating, updating, deleting, and importing/exporting jCard contacts."""

from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from apps.contacts.jcard import parse_jcard_stream
from apps.contacts.models import Contact
from apps.contacts.selectors import list_contacts


def save_contact_for_account(account_key: str, contact: Contact) -> Contact:
    """Assign ``account_key``, synchronize the RFC 7095 jCard, and persist ``contact``."""
    with cast(Any, transaction).atomic():
        contact.account_key = account_key
        contact.full_name = contact.full_name.replace("\r", " ").replace("\n", " ").strip()
        contact.primary_email = contact.primary_email.strip().lower()
        contact.sync_jcard()
        contact.full_clean()
        contact.save()
    return contact


def delete_contact_for_account(account_key: str, contact_id: int) -> bool:
    """Delete one contact owned by ``account_key``."""
    with cast(Any, transaction).atomic():
        deleted_count, _ = (
            cast(Any, Contact).objects.filter(account_key=account_key, pk=contact_id).delete()
        )
    return bool(deleted_count)


def import_jcard_for_account(account_key: str, raw_json: str) -> tuple[int, int]:
    """Parse an RFC 7095 jCard JSON payload and upsert each contact for ``account_key``."""
    try:
        entries = parse_jcard_stream(raw_json)
    except ValueError as exc:
        raise ValidationError(_("Invalid RFC 7095 jCard payload.")) from exc

    created_count = 0
    updated_count = 0
    with cast(Any, transaction).atomic():
        for item in entries:
            existing = (
                cast(Any, Contact)
                .objects.filter(
                    account_key=account_key,
                    primary_email=item.email,
                )
                .first()
            )
            if existing is None:
                contact = Contact(account_key=account_key)
                created_count += 1
            else:
                contact = existing
                updated_count += 1
            contact.full_name = item.full_name
            contact.primary_email = item.email
            contact.phone = item.phone
            contact.organization = item.organization
            contact.job_title = item.job_title
            contact.category = item.category
            contact.notes = item.notes
            contact.sync_jcard()
            contact.full_clean()
            contact.save()
    return created_count, updated_count


def export_jcard_for_account(account_key: str) -> list[list[Any]]:
    """Return the list of canonical RFC 7095 jCard arrays for ``account_key``."""
    contacts = list_contacts(account_key)
    result: list[list[Any]] = []
    for contact in contacts:
        if not contact.jcard:
            contact.sync_jcard()
        result.append(contact.jcard)
    return result
