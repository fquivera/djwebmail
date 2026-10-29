"""Corporate identity and branding models for DjWebmail administration."""

from __future__ import annotations

from typing import Any, cast

from django.db import models
from django.utils.translation import gettext_lazy as _


class CorporateIdentity(models.Model):
    """Singleton model representing the corporate branding of the mail deployment."""

    organization_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name=_("Organization name"),
        help_text=_("The commercial or legal name of the organization or condominium."),
    )
    tagline = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name=_("Tagline / Subtitle"),
        help_text=_("A short descriptive phrase shown next to the identity."),
    )
    tax_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("Fiscal ID (RIF / CIF / NIF / Tax ID)"),
        help_text=_("Official identification number for fiscal or legal purposes."),
    )
    fiscal_address = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Fiscal / Physical address"),
        help_text=_("Complete physical or legal headquarters address."),
    )
    support_email = models.EmailField(
        blank=True,
        default="",
        verbose_name=_("Support email"),
        help_text=_("Primary address where users can request administrative assistance."),
    )
    support_phone = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("Support phone / WhatsApp"),
        help_text=_("Telephone number or messaging link for assistance."),
    )
    website_url = models.URLField(
        blank=True,
        default="",
        max_length=500,
        verbose_name=_("Official website URL"),
        help_text=_("External link to the organization's portal or homepage."),
    )
    terms_url = models.URLField(
        blank=True,
        default="",
        max_length=500,
        verbose_name=_("Terms of service URL"),
        help_text=_("Public link to terms and conditions."),
    )
    privacy_url = models.URLField(
        blank=True,
        default="",
        max_length=500,
        verbose_name=_("Privacy policy URL"),
        help_text=_("Public link to data protection and privacy policy."),
    )
    logo_light_url = models.URLField(
        blank=True,
        default="",
        max_length=500,
        verbose_name=_("Light mode logo URL"),
        help_text=_("Direct image URL to logo on light backgrounds."),
    )
    logo_dark_url = models.URLField(
        blank=True,
        default="",
        max_length=500,
        verbose_name=_("Dark mode logo URL"),
        help_text=_("Direct image URL to logo on dark backgrounds."),
    )
    favicon_url = models.URLField(
        blank=True,
        default="",
        max_length=500,
        verbose_name=_("Favicon URL"),
        help_text=_("Direct image or .ico URL for the browser tab icon."),
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Last updated"))

    class Meta:
        verbose_name = _("Corporate Identity")
        verbose_name_plural = _("Corporate Identity")

    def __str__(self) -> str:
        return str(self.organization_name) or str(_("Default Identity"))

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Enforce singleton constraint."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> CorporateIdentity:
        """Retrieve the singleton instance or create a default one."""
        instance, _ = cast(Any, cls).objects.get_or_create(pk=1)
        return cast(CorporateIdentity, instance)
