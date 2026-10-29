"""Mail account drivers package for apps.mailadmin."""

from apps.mailadmin.drivers.base import (
    BaseMailAccountDriver,
    MailAccountData,
    format_storage_bytes,
)
from apps.mailadmin.drivers.database import DatabaseMailAccountDriver
from apps.mailadmin.drivers.factory import get_account_driver
from apps.mailadmin.drivers.file import FileMailAccountDriver

__all__ = [
    "BaseMailAccountDriver",
    "DatabaseMailAccountDriver",
    "FileMailAccountDriver",
    "MailAccountData",
    "format_storage_bytes",
    "get_account_driver",
]
