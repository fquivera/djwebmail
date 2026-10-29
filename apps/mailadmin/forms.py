"""Forms for the mail administration and branding module."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.accounts.services.password import validate_password_rules
from apps.mailadmin.drivers.factory import get_account_driver
from apps.mailadmin.models import CorporateIdentity


class CorporateIdentityForm(forms.ModelForm):
    """Configuration form for corporate identity, logos, and legal contacts."""

    website_url = forms.URLField(
        required=False,
        assume_scheme="https",
        label=_("Official website URL"),
        widget=forms.URLInput(
            attrs={
                "class": "input w-full",
                "placeholder": "example.com",
            }
        ),
    )
    terms_url = forms.URLField(
        required=False,
        assume_scheme="https",
        label=_("Terms of service URL"),
        widget=forms.URLInput(
            attrs={
                "class": "input w-full",
                "placeholder": "example.com/terms",
            }
        ),
    )
    privacy_url = forms.URLField(
        required=False,
        assume_scheme="https",
        label=_("Privacy policy URL"),
        widget=forms.URLInput(
            attrs={
                "class": "input w-full",
                "placeholder": "example.com/privacy",
            }
        ),
    )
    logo_light_url = forms.URLField(
        required=False,
        assume_scheme="https",
        label=_("Light mode logo URL"),
        widget=forms.URLInput(
            attrs={
                "class": "input w-full",
                "placeholder": "example.com/logo-light.png",
            }
        ),
    )
    logo_dark_url = forms.URLField(
        required=False,
        assume_scheme="https",
        label=_("Dark mode logo URL"),
        widget=forms.URLInput(
            attrs={
                "class": "input w-full",
                "placeholder": "example.com/logo-dark.png",
            }
        ),
    )
    favicon_url = forms.URLField(
        required=False,
        assume_scheme="https",
        label=_("Favicon URL"),
        widget=forms.URLInput(
            attrs={
                "class": "input w-full",
                "placeholder": "example.com/favicon.ico",
            }
        ),
    )

    class Meta:
        model = CorporateIdentity
        fields = (
            "organization_name",
            "tagline",
            "tax_id",
            "fiscal_address",
            "support_email",
            "support_phone",
            "website_url",
            "terms_url",
            "privacy_url",
            "logo_light_file",
            "logo_light_url",
            "logo_dark_file",
            "logo_dark_url",
            "favicon_file",
            "favicon_url",
        )
        labels = {
            "organization_name": _("Organization name"),
            "tagline": _("Tagline / Subtitle"),
            "tax_id": _("Fiscal ID (RIF / CIF / NIF / Tax ID)"),
            "fiscal_address": _("Fiscal / Physical address"),
            "support_email": _("Support email"),
            "support_phone": _("Support phone / WhatsApp"),
            "logo_light_file": _("Light mode logo file"),
            "logo_dark_file": _("Dark mode logo file"),
            "favicon_file": _("Favicon file"),
        }
        widgets = {
            "organization_name": forms.TextInput(
                attrs={
                    "class": "input w-full",
                    "placeholder": _("e.g. Mi Condominio Fácil"),
                }
            ),
            "tagline": forms.TextInput(
                attrs={
                    "class": "input w-full",
                    "placeholder": _("e.g. Servicio de Correo Corporativo"),
                }
            ),
            "tax_id": forms.TextInput(
                attrs={
                    "class": "input w-full",
                    "placeholder": _("e.g. J-12345678-9"),
                }
            ),
            "fiscal_address": forms.Textarea(
                attrs={
                    "class": "textarea w-full",
                    "rows": 3,
                    "placeholder": _("Complete street address, city, state and country"),
                }
            ),
            "support_email": forms.EmailInput(
                attrs={
                    "class": "input w-full",
                    "placeholder": _("soporte@micondominiofacil.com"),
                }
            ),
            "support_phone": forms.TextInput(
                attrs={
                    "class": "input w-full",
                    "placeholder": _("+58 414 1234567"),
                }
            ),
            "logo_light_file": forms.ClearableFileInput(
                attrs={
                    "class": "file-input file-input-bordered file-input-sm w-full",
                    "accept": ".png,.jpg,.jpeg,.svg,.webp,.gif",
                }
            ),
            "logo_dark_file": forms.ClearableFileInput(
                attrs={
                    "class": "file-input file-input-bordered file-input-sm w-full",
                    "accept": ".png,.jpg,.jpeg,.svg,.webp,.gif",
                }
            ),
            "favicon_file": forms.ClearableFileInput(
                attrs={
                    "class": "file-input file-input-bordered file-input-sm w-full",
                    "accept": ".ico,.png,.svg",
                }
            ),
        }

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        pairs = [
            ("logo_light_file", "logo_light_url", _("light mode logo")),
            ("logo_dark_file", "logo_dark_url", _("dark mode logo")),
            ("favicon_file", "favicon_url", _("favicon")),
        ]
        for file_key, url_key, label in pairs:
            file_val = cleaned_data.get(file_key)
            url_val = (cleaned_data.get(url_key) or "").strip()

            has_file = bool(file_val and file_val is not False)
            has_url = bool(url_val)

            if has_file and has_url:
                msg = _("Choose either an image file or a URL for %(asset)s, not both.") % {
                    "asset": label
                }
                self.add_error(file_key, msg)
                self.add_error(url_key, msg)

        return cleaned_data


class MailboxCreateForm(forms.Form):
    """Form to provision a new email account with credentials and quota."""

    email = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(
            attrs={
                "class": "input w-full",
                "placeholder": "user@example.com",
                "autocomplete": "off",
            }
        ),
    )
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "input w-full",
                "placeholder": "••••••••••••",
                "autocomplete": "new-password",
            }
        ),
    )
    confirm_password = forms.CharField(
        label=_("Confirm password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "input w-full",
                "placeholder": "••••••••••••",
                "autocomplete": "new-password",
            }
        ),
    )
    quota_amount = forms.IntegerField(
        label=_("Quota limit"),
        required=False,
        min_value=1,
        widget=forms.NumberInput(
            attrs={
                "class": "input w-32",
                "placeholder": "2",
            }
        ),
    )
    quota_unit = forms.ChoiceField(
        label=_("Unit"),
        choices=[
            ("MB", "MB"),
            ("GB", "GB"),
            ("UNLIMITED", _("Unlimited")),
        ],
        initial="GB",
        widget=forms.Select(attrs={"class": "select"}),
    )
    is_active = forms.BooleanField(
        label=_("Active account"),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"}),
    )

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if "@" not in email:
            raise forms.ValidationError(_("Enter a valid email address with domain."))

        driver = get_account_driver()
        if driver.get_account(email) is not None:
            raise forms.ValidationError(_("An account with this email address already exists."))
        return email

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        email = cleaned_data.get("email") or ""
        password = cleaned_data.get("password") or ""
        confirm = cleaned_data.get("confirm_password") or ""

        if password:
            errors = validate_password_rules(password, email=email)
            if errors:
                self.add_error("password", errors[0])

            if password != confirm:
                self.add_error("confirm_password", _("Passwords do not match."))

        unit = cleaned_data.get("quota_unit")
        amount = cleaned_data.get("quota_amount")
        if unit == "UNLIMITED":
            cleaned_data["quota_bytes"] = None
        elif amount:
            if unit == "MB":
                cleaned_data["quota_bytes"] = amount * 1024 * 1024
            elif unit == "GB":
                cleaned_data["quota_bytes"] = amount * 1024 * 1024 * 1024
        else:
            cleaned_data["quota_bytes"] = None

        return cleaned_data


class MailboxEditForm(forms.Form):
    """Form to edit quota, active status, or reset password of an existing mailbox."""

    password = forms.CharField(
        label=_("New password (optional)"),
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "input w-full",
                "placeholder": _("Leave blank to keep unchanged"),
                "autocomplete": "new-password",
            }
        ),
    )
    confirm_password = forms.CharField(
        label=_("Confirm new password"),
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "input w-full",
                "placeholder": _("Leave blank to keep unchanged"),
                "autocomplete": "new-password",
            }
        ),
    )
    quota_amount = forms.IntegerField(
        label=_("Quota limit"),
        required=False,
        min_value=1,
        widget=forms.NumberInput(
            attrs={
                "class": "input w-32",
                "placeholder": "2",
            }
        ),
    )
    quota_unit = forms.ChoiceField(
        label=_("Unit"),
        choices=[
            ("MB", "MB"),
            ("GB", "GB"),
            ("UNLIMITED", _("Unlimited")),
        ],
        widget=forms.Select(attrs={"class": "select"}),
    )
    is_active = forms.BooleanField(
        label=_("Active account"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"}),
    )

    def __init__(self, *args: Any, email: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.target_email = email

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        password = cleaned_data.get("password") or ""
        confirm = cleaned_data.get("confirm_password") or ""

        if password:
            errors = validate_password_rules(password, email=self.target_email)
            if errors:
                self.add_error("password", errors[0])

            if password != confirm:
                self.add_error("confirm_password", _("Passwords do not match."))

        unit = cleaned_data.get("quota_unit")
        amount = cleaned_data.get("quota_amount")
        if unit == "UNLIMITED":
            cleaned_data["quota_bytes"] = None
            cleaned_data["clear_quota"] = True
        elif amount:
            if unit == "MB":
                cleaned_data["quota_bytes"] = amount * 1024 * 1024
            elif unit == "GB":
                cleaned_data["quota_bytes"] = amount * 1024 * 1024 * 1024
            cleaned_data["clear_quota"] = False
        else:
            cleaned_data["quota_bytes"] = None
            cleaned_data["clear_quota"] = True

        return cleaned_data
