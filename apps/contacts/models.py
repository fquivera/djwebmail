"""Per-account contact stored with a canonical RFC 7095 jCard payload."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from email.utils import formataddr
from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.accounts.constants import ACCOUNT_KEY_MAX_LENGTH
from apps.contacts.constants import (
    CONTACT_CATEGORY_MAX_LENGTH,
    CONTACT_NAME_MAX_LENGTH,
    CONTACT_NOTE_MAX_LENGTH,
    CONTACT_ORG_MAX_LENGTH,
    CONTACT_PHONE_MAX_LENGTH,
    CONTACT_TITLE_MAX_LENGTH,
)
from apps.contacts.jcard import ContactData, build_jcard, parse_jcard


class Contact(models.Model):
    """One address-book entry scoped to a mail account via ``account_key``."""

    account_key = cast(
        str,
        models.CharField(max_length=ACCOUNT_KEY_MAX_LENGTH, db_index=True),
    )
    uid = cast(
        uuid.UUID,
        models.UUIDField(default=uuid.uuid4, editable=False),
    )
    full_name = cast(
        str,
        models.CharField(max_length=CONTACT_NAME_MAX_LENGTH),
    )
    primary_email = cast(
        str,
        models.EmailField(db_index=True),
    )
    phone = cast(
        str,
        models.CharField(max_length=CONTACT_PHONE_MAX_LENGTH, blank=True, default=""),
    )
    organization = cast(
        str,
        models.CharField(max_length=CONTACT_ORG_MAX_LENGTH, blank=True, default=""),
    )
    job_title = cast(
        str,
        models.CharField(max_length=CONTACT_TITLE_MAX_LENGTH, blank=True, default=""),
    )
    category = cast(
        str,
        models.CharField(max_length=CONTACT_CATEGORY_MAX_LENGTH, blank=True, default=""),
    )
    notes = cast(
        str,
        models.TextField(max_length=CONTACT_NOTE_MAX_LENGTH, blank=True, default=""),
    )
    jcard = cast(
        list[Any],
        models.JSONField(default=list, blank=True),
    )
    created_at = cast(datetime, models.DateTimeField(auto_now_add=True))
    updated_at = cast(datetime, models.DateTimeField(auto_now=True))

    class Meta:
        ordering = ["full_name", "primary_email"]
        verbose_name = gettext_lazy("contact")
        verbose_name_plural = gettext_lazy("contacts")
        constraints = [
            models.UniqueConstraint(
                fields=["account_key", "primary_email"],
                name="uniq_contact_email_per_account",
            )
        ]

    def __str__(self) -> str:
        return self.formatted_address

    @property
    def formatted_address(self) -> str:
        """Return ``"Full Name <email>"`` for compose fields."""
        clean_name = self.full_name.replace("\r", " ").replace("\n", " ").strip()
        clean_email = self.primary_email.strip()
        if clean_name and clean_email:
            return formataddr((clean_name, clean_email))
        return clean_email

    @property
    def jcard_pretty(self) -> str:
        """Return the contact's RFC 7095 jCard formatted as indented JSON."""
        return json.dumps(self.jcard, ensure_ascii=False, indent=2)

    def sync_jcard(self) -> None:
        """Rebuild the canonical RFC 7095 jCard array from the model fields."""
        self.jcard = build_jcard(
            ContactData(
                uid=str(self.uid or uuid.uuid4()),
                full_name=self.full_name,
                email=self.primary_email,
                phone=self.phone,
                organization=self.organization,
                job_title=self.job_title,
                category=self.category,
                notes=self.notes,
            )
        )

    def clean(self) -> None:
        super().clean()
        self.full_name = self.full_name.replace("\r", " ").replace("\n", " ").strip()
        self.primary_email = self.primary_email.strip().lower()
        self.phone = self.phone.strip()
        self.organization = self.organization.strip()
        self.job_title = self.job_title.strip()
        self.category = self.category.strip()
        self.notes = self.notes.strip()

        if not self.primary_email:
            return
        if not self.jcard:
            self.sync_jcard()
        try:
            parse_jcard(self.jcard)
        except ValueError as exc:
            raise ValidationError(_("Invalid RFC 7095 jCard representation.")) from exc
