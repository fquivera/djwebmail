"""Factory to resolve the configured mail account storage driver."""

from __future__ import annotations

import os

from django.conf import settings

from apps.mailadmin.drivers.base import BaseMailAccountDriver
from apps.mailadmin.drivers.database import DatabaseMailAccountDriver
from apps.mailadmin.drivers.file import FileMailAccountDriver


def get_account_driver() -> BaseMailAccountDriver:
    """Return an instantiated driver based on settings.MAIL_ADMIN_DRIVER and environment."""
    driver_type = getattr(settings, "MAIL_ADMIN_DRIVER", "auto").strip().lower()
    accounts_file = getattr(settings, "MAIL_ACCOUNTS_FILE", "").strip()
    virtual_file = getattr(settings, "MAIL_VIRTUAL_FILE", "").strip()

    if driver_type == "file":
        return FileMailAccountDriver(accounts_file=accounts_file, virtual_file=virtual_file)
    elif driver_type == "database":
        return DatabaseMailAccountDriver()

    # "auto": if accounts_file is provided and exists, use file driver; otherwise database.
    if accounts_file and os.path.isfile(accounts_file):
        return FileMailAccountDriver(accounts_file=accounts_file, virtual_file=virtual_file)
    return DatabaseMailAccountDriver()
