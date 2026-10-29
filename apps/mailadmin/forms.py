"""Forms for the mail administration and branding module."""

from __future__ import annotations

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
            "logo_light_url",
            "logo_dark_url",
            "favicon_url",
        )
        labels = {
            "organization_name": _("Organization name"),
            "tagline": _("Tagline / Subtitle"),
            "tax_id": _("Fiscal ID (RIF / CIF / NIF / Tax ID)"),
            "fiscal_address": _("Fiscal / Physical address"),
            "support_email": _("Support email"),
            "support_phone": _("Support phone / WhatsApp"),
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
        }
