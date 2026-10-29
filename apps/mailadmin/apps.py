from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MailadminConfig(AppConfig):
    name = "apps.mailadmin"
    verbose_name = _("Mail Administration")
