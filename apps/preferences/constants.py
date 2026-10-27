"""Domain choices for per-account presentation preferences."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Theme(models.TextChoices):
    SYSTEM = "system", _("System")
    LIGHT = "light", _("Light")
    DARK = "dark", _("Dark")


class Density(models.TextChoices):
    COMPACT = "compact", _("Compact")
    COMFORTABLE = "comfortable", _("Comfortable")


class Layout(models.TextChoices):
    SIDE = "side", _("Side by side")
    TOP = "top", _("Top")


class RemoteImages(models.TextChoices):
    ASK = "ask", _("Ask before loading")
    ALWAYS = "always", _("Always load")
    NEVER = "never", _("Never load")


PAGE_SIZE_MIN = 1
DISPLAY_NAME_MAX_LENGTH = 120
ACCOUNT_LABEL_MAX_LENGTH = 64
