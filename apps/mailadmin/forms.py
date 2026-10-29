"""Forms for the mail administration and branding module."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

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
