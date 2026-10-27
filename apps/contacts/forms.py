"""Forms for creating, editing, and importing RFC 7095 jCard contacts."""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.contacts.constants import (
    CONTACT_CATEGORY_MAX_LENGTH,
    CONTACT_NAME_MAX_LENGTH,
    CONTACT_NOTE_MAX_LENGTH,
    CONTACT_ORG_MAX_LENGTH,
    CONTACT_PHONE_MAX_LENGTH,
    CONTACT_TITLE_MAX_LENGTH,
)
from apps.contacts.models import Contact


class ContactForm(forms.ModelForm):
    """Form for creating or updating one contact."""

    class Meta:
        model = Contact
        fields = (
            "full_name",
            "primary_email",
            "phone",
            "organization",
            "job_title",
            "category",
            "notes",
        )
        labels = {
            "full_name": _("Full name"),
            "primary_email": _("Email address"),
            "phone": _("Phone"),
            "organization": _("Organization"),
            "job_title": _("Job title"),
            "category": _("Label / Group"),
            "notes": _("Notes"),
        }
        widgets = {
            "full_name": forms.TextInput(
                attrs={
                    "class": "input input-bordered input-sm w-full",
                    "maxlength": CONTACT_NAME_MAX_LENGTH,
                    "autocomplete": "name",
                }
            ),
            "primary_email": forms.EmailInput(
                attrs={
                    "class": "input input-bordered input-sm w-full",
                    "autocomplete": "email",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "input input-bordered input-sm w-full",
                    "maxlength": CONTACT_PHONE_MAX_LENGTH,
                    "autocomplete": "tel",
                }
            ),
            "organization": forms.TextInput(
                attrs={
                    "class": "input input-bordered input-sm w-full",
                    "maxlength": CONTACT_ORG_MAX_LENGTH,
                    "autocomplete": "organization",
                }
            ),
            "job_title": forms.TextInput(
                attrs={
                    "class": "input input-bordered input-sm w-full",
                    "maxlength": CONTACT_TITLE_MAX_LENGTH,
                }
            ),
            "category": forms.TextInput(
                attrs={
                    "class": "input input-bordered input-sm w-full",
                    "maxlength": CONTACT_CATEGORY_MAX_LENGTH,
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered textarea-sm w-full",
                    "rows": 2,
                    "maxlength": CONTACT_NOTE_MAX_LENGTH,
                }
            ),
        }

    def __init__(self, *args: Any, account_key: str = "", **kwargs: Any) -> None:
        self.account_key = account_key
        super().__init__(*args, **kwargs)
        if self.account_key:
            self.instance.account_key = self.account_key

    def clean_primary_email(self) -> str:
        value = self.cleaned_data.get("primary_email")
        email = value.strip().lower() if isinstance(value, str) else ""
        if self.account_key and email:
            qs = cast(Any, Contact).objects.filter(
                account_key=self.account_key,
                primary_email=email,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(_("A contact with this email address already exists."))
        return email
