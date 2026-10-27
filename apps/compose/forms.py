"""Forms for composing and sending mail."""

from __future__ import annotations

from email.utils import getaddresses

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _

from apps.compose.constants import MAX_RECIPIENTS, MAX_SUBJECT_LENGTH


class ComposeForm(forms.Form):
    """Recipients, subject, and plain-text body for one outgoing message."""

    to = forms.CharField(
        label=_("To"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "class": "input w-full",
                "placeholder": _("name@example.com, another@example.com"),
            }
        ),
    )
    cc = forms.CharField(
        label=_("Cc"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "class": "input w-full",
            }
        ),
    )
    bcc = forms.CharField(
        label=_("Bcc"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "class": "input w-full",
            }
        ),
    )
    subject = forms.CharField(
        label=_("Subject"),
        max_length=MAX_SUBJECT_LENGTH,
        required=False,
        widget=forms.TextInput(attrs={"class": "input w-full"}),
    )
    body = forms.CharField(
        label=_("Message"),
        required=False,
        widget=forms.Textarea(attrs={"class": "textarea w-full", "rows": 12}),
    )

    def clean_to(self) -> list[str]:
        return _clean_addresses(self.cleaned_data["to"], required=True)

    def clean_cc(self) -> list[str]:
        return _clean_addresses(self.cleaned_data["cc"], required=False)

    def clean_bcc(self) -> list[str]:
        return _clean_addresses(self.cleaned_data.get("bcc", ""), required=False)

    def clean_subject(self) -> str:
        subject = self.cleaned_data["subject"]
        if "\r" in subject or "\n" in subject:
            raise ValidationError(_("The subject cannot contain line breaks."))
        return subject


def _clean_addresses(value: str, *, required: bool) -> list[str]:
    if "\r" in value or "\n" in value:
        raise ValidationError(_("Enter addresses separated by commas."))

    addresses = [address for _name, address in getaddresses([value]) if address]
    if not addresses:
        if required:
            raise ValidationError(_("Enter at least one recipient."))
        return []
    if len(addresses) > MAX_RECIPIENTS:
        raise ValidationError(
            _("You can address at most %(maximum)s recipients.") % {"maximum": MAX_RECIPIENTS}
        )

    for address in addresses:
        try:
            validate_email(address)
        except ValidationError as exc:
            raise ValidationError(_("Enter valid email addresses.")) from exc
    return addresses
