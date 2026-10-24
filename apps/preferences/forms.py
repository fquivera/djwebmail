"""Form for the preferences page."""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from zoneinfo import available_timezones

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from apps.preferences.constants import PAGE_SIZE_MIN
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
        fields = ("language", "timezone", "theme", "density", "page_size")
        labels = {
            "language": _("Language"),
            "timezone": _("Time zone"),
            "theme": _("Theme"),
            "density": _("Density"),
            "page_size": _("Messages per page"),
        }
        help_texts = {
            "language": _("Applies to this account after saving."),
            "timezone": _("Used for message dates and times."),
            "theme": _("System follows the operating system preference."),
            "density": _("Compact shows more messages in the list."),
            "page_size": _("Between %(minimum)s and %(maximum)s.")
            % {"minimum": PAGE_SIZE_MIN, "maximum": settings.MAIL_MAX_PAGE_SIZE},
        }
        widgets = {
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
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["language"].widget.choices = settings.LANGUAGES
        self.fields["timezone"].widget.choices = timezone_choices()
        auto_id = self.auto_id
        if isinstance(auto_id, str):
            for name, field in self.fields.items():
                if field.help_text:
                    field.widget.attrs["aria-describedby"] = f"{auto_id % name}_help"
