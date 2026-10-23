"""Forms for IMAP-backed webmail authentication."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.accounts.exceptions import MailAddressError
from apps.accounts.services.account import normalize_email


class LoginForm(forms.Form):
    """Email and password submitted to the deployment's IMAP server."""

    email = forms.EmailField(
        label=_("Email address"),
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "username",
                "autofocus": True,
                "class": "input w-full",
            }
        ),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "class": "input w-full",
            }
        ),
    )

    def clean_email(self) -> str:
        email = self.cleaned_data["email"]
        try:
            return normalize_email(email)
        except MailAddressError as exc:
            raise forms.ValidationError(_("Enter a valid email address.")) from exc
