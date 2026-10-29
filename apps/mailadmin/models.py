"""Corporate identity and branding models for DjWebmail administration."""

from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import DatabaseError, OperationalError, ProgrammingError, models
from django.utils.translation import gettext_lazy as _

IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "svg", "webp", "gif"]
FAVICON_EXTENSIONS = ["ico", "png", "svg"]


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
    logo_light_file = models.FileField(
        upload_to="branding/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=IMAGE_EXTENSIONS)],
        verbose_name=_("Light mode logo file"),
        help_text=_("Image file (.png, .jpg, .svg, .webp) for light backgrounds."),
    )
    logo_light_url = models.URLField(
        blank=True,
        default="",
        max_length=500,
        verbose_name=_("Light mode logo URL"),
        help_text=_("Direct image URL to logo on light backgrounds."),
    )
    logo_dark_file = models.FileField(
        upload_to="branding/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=IMAGE_EXTENSIONS)],
        verbose_name=_("Dark mode logo file"),
        help_text=_("Image file (.png, .jpg, .svg, .webp) for dark backgrounds."),
    )
    logo_dark_url = models.URLField(
        blank=True,
        default="",
        max_length=500,
        verbose_name=_("Dark mode logo URL"),
        help_text=_("Direct image URL to logo on dark backgrounds."),
    )
    favicon_file = models.FileField(
        upload_to="branding/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=FAVICON_EXTENSIONS)],
        verbose_name=_("Favicon file"),
        help_text=_("Browser tab icon file (.ico, .png, .svg)."),
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
        self.full_clean()
        self.pk = 1
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if self.logo_light_file and self.logo_light_url:
            msg = _("Choose either a file or a URL for the light mode logo, not both.")
            errors["logo_light_file"] = str(msg)
            errors["logo_light_url"] = str(msg)

        if self.logo_dark_file and self.logo_dark_url:
            msg = _("Choose either a file or a URL for the dark mode logo, not both.")
            errors["logo_dark_file"] = str(msg)
            errors["logo_dark_url"] = str(msg)

        if self.favicon_file and self.favicon_url:
            msg = _("Choose either a file or a URL for the favicon, not both.")
            errors["favicon_file"] = str(msg)
            errors["favicon_url"] = str(msg)

        if errors:
            raise ValidationError(errors)

    @property
    def effective_logo_light_url(self) -> str:
        file = cast(Any, self.logo_light_file)
        if file:
            try:
                return str(file.url)
            except ValueError:
                pass
        return str(self.logo_light_url) if self.logo_light_url else ""

    @property
    def effective_logo_dark_url(self) -> str:
        file = cast(Any, self.logo_dark_file)
        if file:
            try:
                return str(file.url)
            except ValueError:
                pass
        return str(self.logo_dark_url) if self.logo_dark_url else ""

    @property
    def effective_favicon_url(self) -> str:
        file = cast(Any, self.favicon_file)
        if file:
            try:
                return str(file.url)
            except ValueError:
                pass
        return str(self.favicon_url) if self.favicon_url else ""

    @classmethod
    def get_solo(cls) -> CorporateIdentity:
        """Retrieve the singleton instance or create a default one.

        Falls back gracefully to an unsaved default instance if the database table
        has not been migrated yet (e.g. during initial setup or rolling deploys).
        """
        try:
            instance, _ = cast(Any, cls).objects.get_or_create(pk=1)
            return cast(CorporateIdentity, instance)
        except (DatabaseError, ProgrammingError, OperationalError):
            return cls(pk=1)


class ManagedMailbox(models.Model):
    """Managed email account and storage quota in the administration database."""

    objects: Any = models.Manager()

    email = cast(
        str,
        models.EmailField(
            unique=True,
            verbose_name=_("Email address"),
            help_text=_("Full email address of the account (e.g. user@domain.com)."),
        ),
    )
    password_hash = cast(
        str,
        models.CharField(
            max_length=255,
            verbose_name=_("Password hash"),
            help_text=_("Cryptographic password hash (e.g. {SHA512-CRYPT})."),
        ),
    )
    quota_bytes = cast(
        int | None,
        models.BigIntegerField(
            null=True,
            blank=True,
            verbose_name=_("Storage quota (bytes)"),
            help_text=str(_("Storage space limit in bytes. Leave empty for unlimited quota.")),
        ),
    )
    is_active = cast(
        bool,
        models.BooleanField(
            default=True,  # pyright: ignore[reportArgumentType]
            verbose_name=_("Active"),
            help_text=str(
                _(
                    "Designates whether this mailbox is allowed to "
                    "authenticate and receive messages."
                )
            ),
        ),
    )
    created_at = cast(
        Any,
        models.DateTimeField(
            auto_now_add=True,
            verbose_name=_("Created at"),
        ),
    )
    updated_at = cast(
        Any,
        models.DateTimeField(
            auto_now=True,
            verbose_name=_("Updated at"),
        ),
    )

    class Meta:
        verbose_name = _("Managed mailbox")
        verbose_name_plural = _("Managed mailboxes")
        ordering = ["email"]

    def __str__(self) -> str:
        return self.email

    @property
    def username(self) -> str:
        return self.email.split("@")[0]

    @property
    def domain(self) -> str:
        return self.email.split("@")[1] if "@" in self.email else ""

    @property
    def quota_display(self) -> str:
        if self.quota_bytes is None:
            return str(_("Unlimited"))
        if self.quota_bytes >= 1024 * 1024 * 1024:
            val = self.quota_bytes / (1024 * 1024 * 1024)
            return f"{val:.1f} GB".replace(".0 GB", " GB")
        if self.quota_bytes >= 1024 * 1024:
            val = self.quota_bytes / (1024 * 1024)
            return f"{val:.1f} MB".replace(".0 MB", " MB")
        return f"{self.quota_bytes} B"
