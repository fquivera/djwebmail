"""Read queries for per-account contacts."""

from __future__ import annotations

from typing import Any, cast

from django.db.models import Q

from apps.contacts.constants import MAX_CONTACTS_AUTOCOMPLETE
from apps.contacts.models import Contact


def list_contacts(account_key: str, query: str = "") -> list[Contact]:
    """Return contacts belonging to ``account_key``, filtered by ``query`` when provided."""
    if not account_key:
        return []
    qs = cast(Any, Contact).objects.filter(account_key=account_key)
    needle = query.strip()
    if needle:
        predicate = (
            cast(Any, Q(full_name__icontains=needle))
            | cast(Any, Q(primary_email__icontains=needle))
            | cast(Any, Q(organization__icontains=needle))
            | cast(Any, Q(category__icontains=needle))
            | cast(Any, Q(phone__icontains=needle))
        )
        qs = qs.filter(predicate)
    return list(qs.order_by("full_name", "primary_email"))


def get_contact(account_key: str, contact_id: int) -> Contact | None:
    """Return one contact owned by ``account_key`` or ``None``."""
    if not account_key:
        return None
    return cast(Any, Contact).objects.filter(account_key=account_key, pk=contact_id).first()


def list_contact_suggestions(account_key: str) -> list[str]:
    """Return formatted ``"Name <email>"`` suggestions for compose autocomplete."""
    if not account_key:
        return []
    contacts = list(
        cast(Any, Contact)
        .objects.filter(account_key=account_key)
        .order_by("full_name", "primary_email")[:MAX_CONTACTS_AUTOCOMPLETE]
    )
    return [contact.formatted_address for contact in contacts]
