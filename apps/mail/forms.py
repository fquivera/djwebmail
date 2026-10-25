"""Validated search filters for the message list."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.mail.constants import (
    SEARCH_ADDRESS_MAX_LENGTH,
    SEARCH_QUERY_MAX_LENGTH,
    SEARCH_SUBJECT_MAX_LENGTH,
)


class NamedTextInput(forms.TextInput):
    """Text input whose submitted name differs from the Python field name.

    ``from`` is a Python keyword, so the form field is called ``from_`` while
    the public query parameter stays ``from`` (the contract documented in
    ``docs/mail-search.md``).
    """

    def __init__(self, *args: Any, input_name: str, **kwargs: Any) -> None:
        self.input_name = input_name
        super().__init__(*args, **kwargs)

    def get_context(
        self,
        name: str,
        value: Any,
        attrs: dict[str, Any] | None,
    ) -> dict[str, Any]:
        context = super().get_context(name, value, attrs)
        context["widget"]["name"] = self.input_name
        return context


class MailSearchForm(forms.Form):
    """Search parameters accepted by ``/mail/search/``."""

    folder = forms.CharField(required=False, widget=forms.HiddenInput)
    q = forms.CharField(
        label=_("Search this folder"),
        required=False,
        max_length=SEARCH_QUERY_MAX_LENGTH,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered input-sm w-full",
                "type": "search",
                "autocomplete": "off",
            }
        ),
    )
    from_ = forms.CharField(
        label=_("From"),
        required=False,
        max_length=SEARCH_ADDRESS_MAX_LENGTH,
        strip=True,
        widget=NamedTextInput(
            input_name="from",
            attrs={"class": "input input-bordered input-sm w-full"},
        ),
    )
    to = forms.CharField(
        label=_("To"),
        required=False,
        max_length=SEARCH_ADDRESS_MAX_LENGTH,
        strip=True,
        widget=forms.TextInput(attrs={"class": "input input-bordered input-sm w-full"}),
    )
    subject = forms.CharField(
        label=_("Subject"),
        required=False,
        max_length=SEARCH_SUBJECT_MAX_LENGTH,
        strip=True,
        widget=forms.TextInput(attrs={"class": "input input-bordered input-sm w-full"}),
    )
    date_from = forms.DateField(
        label=_("From date"),
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"class": "input input-bordered input-sm w-full", "type": "date"},
        ),
    )
    date_to = forms.DateField(
        label=_("To date"),
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"class": "input input-bordered input-sm w-full", "type": "date"},
        ),
    )
    unread = forms.BooleanField(
        label=_("Unread only"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox checkbox-sm"}),
    )

    def __init__(self, data: Any = None, *args: Any, **kwargs: Any) -> None:
        if data is not None:
            data = data.copy()
            if "from" in data and "from_" not in data:
                data["from_"] = data["from"]
        super().__init__(data, *args, **kwargs)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if date_from and date_to and date_from > date_to:
            self.add_error(
                "date_to",
                _("End date must be on or after start date."),
            )
        return cleaned
