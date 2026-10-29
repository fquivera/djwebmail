"""Form for the preferences page."""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from zoneinfo import available_timezones

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.accounts.constants import PASSWORD_MIN_LENGTH
from apps.accounts.services.password import validate_password_rules
from apps.preferences.constants import (
    ACCOUNT_LABEL_MAX_LENGTH,
    DISPLAY_NAME_MAX_LENGTH,
    PAGE_SIZE_MIN,
    RemoteImages,
)
from apps.preferences.models import MailPreference


@lru_cache(maxsize=1)
def timezone_choices() -> tuple[tuple[str, str], ...]:
    """Return the installed IANA zones, with a safe deployment fallback."""
    names = sorted(available_timezones())
    if not names:
        names = [settings.TIME_ZONE]
    return tuple((name, name) for name in names)


class MailPreferenceForm(forms.ModelForm):
    """Editable presentation choices for one mail account."""

    class Meta:
        model = MailPreference
        fields = (
            "display_name",
            "account_label",
            "language",
            "timezone",
            "theme",
            "density",
            "page_size",
            "remote_images",
            "notifications_enabled",
            "notification_sound_enabled",
            "signature_html",
        )
        labels = {
            "display_name": _("Owner name"),
            "account_label": _("Account label"),
            "language": _("Language"),
            "timezone": _("Time zone"),
            "theme": _("Theme"),
            "density": _("Density"),
            "page_size": _("Messages per page"),
            "remote_images": _("Remote images"),
            "notifications_enabled": _("Desktop notifications"),
            "notification_sound_enabled": _("Notification sound"),
            "signature_html": _("Signature"),
        }
        help_texts = {
            "display_name": _("Shown as the sender name on outgoing messages."),
            "account_label": _(
                "Optional tag to identify this mailbox (for example, Work or Admin)."
            ),
            "language": _("Applies to this account after saving."),
            "timezone": _("Used for message dates and times."),
            "theme": _("System follows the operating system preference."),
            "density": _("Compact shows more messages in the list."),
            "page_size": _("Between %(minimum)s and %(maximum)s.")
            % {"minimum": PAGE_SIZE_MIN, "maximum": settings.MAIL_MAX_PAGE_SIZE},
            "remote_images": _("Controls whether external images are loaded through the proxy."),
            "notifications_enabled": _(
                "Show desktop notifications when new emails arrive in your inbox."
            ),
            "notification_sound_enabled": _("Play an audio chime when new emails arrive."),
            "signature_html": _("Appended automatically when composing a new message or reply."),
        }
        widgets = {
            "display_name": forms.TextInput(
                attrs={
                    "class": "input w-full",
                    "maxlength": DISPLAY_NAME_MAX_LENGTH,
                    "autocomplete": "name",
                }
            ),
            "account_label": forms.TextInput(
                attrs={
                    "class": "input w-full",
                    "maxlength": ACCOUNT_LABEL_MAX_LENGTH,
                }
            ),
            "language": forms.Select(attrs={"class": "select w-full"}),
            "timezone": forms.Select(attrs={"class": "select w-full"}),
            "theme": forms.Select(attrs={"class": "select w-full"}),
            "density": forms.Select(attrs={"class": "select w-full"}),
            "page_size": forms.NumberInput(
                attrs={
                    "class": "input w-full",
                    "min": PAGE_SIZE_MIN,
                    "max": settings.MAIL_MAX_PAGE_SIZE,
                }
            ),
            "remote_images": forms.Select(attrs={"class": "select w-full"}),
            "notifications_enabled": forms.CheckboxInput(
                attrs={"class": "toggle toggle-primary toggle-sm"}
            ),
            "notification_sound_enabled": forms.CheckboxInput(
                attrs={"class": "toggle toggle-primary toggle-sm"}
            ),
            "signature_html": forms.Textarea(
                attrs={
                    "class": "textarea w-full text-sm",
                    "rows": 3,
                }
            ),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["language"].widget.choices = settings.LANGUAGES
        self.fields["timezone"].widget.choices = timezone_choices()
        self.fields["display_name"].required = False
        self.fields["account_label"].required = False
        self.fields["remote_images"].required = False
        self.fields["notifications_enabled"].required = False
        self.fields["notification_sound_enabled"].required = False
        self.fields["signature_html"].required = False
        auto_id = self.auto_id
        if isinstance(auto_id, str):
            for name, field in self.fields.items():
                if field.help_text:
                    field.widget.attrs["aria-describedby"] = f"{auto_id % name}_help"

    def clean_display_name(self) -> str:
        value = self.cleaned_data.get("display_name")
        text = value if isinstance(value, str) else ""
        if "\r" in text or "\n" in text:
            raise ValidationError(_("This field cannot contain line breaks."))
        return text.strip()

    def clean_account_label(self) -> str:
        value = self.cleaned_data.get("account_label")
        text = value if isinstance(value, str) else ""
        if "\r" in text or "\n" in text:
            raise ValidationError(_("This field cannot contain line breaks."))
        return text.strip()

    def clean_remote_images(self) -> str:
        value = self.cleaned_data.get("remote_images")
        if isinstance(value, str) and value in RemoteImages.values:
            return value
        instance_value = getattr(self.instance, "remote_images", "")
        if isinstance(instance_value, str) and instance_value in RemoteImages.values:
            return instance_value
        return RemoteImages.ASK


class ChangePasswordForm(forms.Form):
    """Form to change the account password with OWASP/NIST validation rules."""

    current_password = forms.CharField(
        label=_("Current password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "input w-full",
                "autocomplete": "current-password",
                "placeholder": "••••••••••••",
            }
        ),
    )
    new_password = forms.CharField(
        label=_("New password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "input w-full",
                "autocomplete": "new-password",
                "minlength": PASSWORD_MIN_LENGTH,
                "placeholder": "••••••••••••",
                "data-password-input": "new",
            }
        ),
        help_text=_("Minimum 12 characters, including uppercase, lowercase, numbers, and symbols."),
    )
    confirm_password = forms.CharField(
        label=_("Confirm new password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "input w-full",
                "autocomplete": "new-password",
                "minlength": PASSWORD_MIN_LENGTH,
                "placeholder": "••••••••••••",
                "data-password-input": "confirm",
            }
        ),
    )

    def __init__(self, *args: Any, email: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.email = email

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        current_password = cleaned_data.get("current_password") or ""
        new_password = cleaned_data.get("new_password") or ""
        confirm_password = cleaned_data.get("confirm_password") or ""

        if new_password and confirm_password and new_password != confirm_password:
            self.add_error("confirm_password", _("The new passwords do not match."))

        if new_password:
            errors = validate_password_rules(
                new_password,
                current_password=current_password,
                email=self.email,
            )
            for err in errors:
                self.add_error("new_password", err)

        return cleaned_data
