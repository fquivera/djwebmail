"""Base interface and dataclasses for mail account drivers."""

from __future__ import annotations

import abc
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from django.utils.translation import gettext as _


def format_storage_bytes(num_bytes: int | None) -> str:
    """Format bytes into a localized human-readable string (e.g. '2 GB', '500 MB', 'Unlimited')."""
    if num_bytes is None:
        return _("Unlimited")
    if num_bytes >= 1024 * 1024 * 1024:
        val = num_bytes / (1024 * 1024 * 1024)
        return f"{val:.1f} GB".replace(".0 GB", " GB")
    if num_bytes >= 1024 * 1024:
        val = num_bytes / (1024 * 1024)
        return f"{val:.1f} MB".replace(".0 MB", " MB")
    if num_bytes >= 1024:
        val = num_bytes / 1024
        return f"{val:.1f} KB".replace(".0 KB", " KB")
    return f"{num_bytes} B"


@dataclass(slots=True)
class MailAccountData:
    """Normalized data representation of a mail account across different backends."""

    email: str
    is_active: bool = True
    quota_bytes: int | None = None
    used_bytes: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def username(self) -> str:
        return self.email.split("@")[0]

    @property
    def domain(self) -> str:
        return self.email.split("@")[1] if "@" in self.email else ""

    @property
    def quota_display(self) -> str:
        return format_storage_bytes(self.quota_bytes)

    @property
    def used_display(self) -> str:
        if self.used_bytes is None:
            return "0 B"
        return format_storage_bytes(self.used_bytes)

    @property
    def quota_percent(self) -> int | None:
        if self.quota_bytes is not None and self.used_bytes is not None and self.quota_bytes > 0:
            pct = int((self.used_bytes / self.quota_bytes) * 100)
            return min(100, max(0, pct))
        return None


@dataclass(slots=True)
class MailAliasData:
    """Normalized data representation of a virtual alias or distribution list."""

    source: str
    destinations: list[str]
    name: str = ""
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_distribution_list(self) -> bool:
        """Returns True if there are multiple destination recipients."""
        return len(self.destinations) > 1

    @property
    def destination_count(self) -> int:
        return len(self.destinations)

    @property
    def destinations_display(self) -> str:
        return ", ".join(self.destinations)

    @property
    def domain(self) -> str:
        return self.source.split("@")[1] if "@" in self.source else ""


class BaseMailAccountDriver(abc.ABC):
    """Abstract base class for mail server account storage drivers."""

    @abc.abstractmethod
    def list_accounts(
        self,
        search: str = "",
        is_active: bool | None = None,
    ) -> list[MailAccountData]:
        """Return a list of mail accounts matching optional search query and active status."""

    @abc.abstractmethod
    def get_account(self, email: str) -> MailAccountData | None:
        """Retrieve a single mail account by email address, or None if not found."""

    @abc.abstractmethod
    def create_account(
        self,
        email: str,
        password: str,
        quota_bytes: int | None = None,
        is_active: bool = True,
    ) -> MailAccountData:
        """Create a new mail account with encrypted credentials and optional quota."""

    @abc.abstractmethod
    def update_account(
        self,
        email: str,
        password: str | None = None,
        quota_bytes: int | None = None,
        is_active: bool | None = None,
        clear_quota: bool = False,
    ) -> MailAccountData:
        """Update password, quota, or active status of an existing account."""

    @abc.abstractmethod
    def delete_account(self, email: str) -> bool:
        """Delete an existing mail account. Return True if deleted, False if not found."""

    def set_password(self, email: str, new_password: str) -> None:
        """Helper to update only the account password."""
        self.update_account(email, password=new_password)

    @abc.abstractmethod
    def list_aliases(
        self,
        search: str = "",
        is_active: bool | None = None,
    ) -> list[MailAliasData]:
        """Return a list of virtual aliases and distribution lists."""

    @abc.abstractmethod
    def get_alias(self, source: str) -> MailAliasData | None:
        """Retrieve a single alias by source address, or None if not found."""

    @abc.abstractmethod
    def create_alias(
        self,
        source: str,
        destinations: Sequence[str],
        name: str = "",
        is_active: bool = True,
    ) -> MailAliasData:
        """Create a new alias or distribution list."""

    @abc.abstractmethod
    def update_alias(
        self,
        source: str,
        destinations: Sequence[str] | None = None,
        name: str | None = None,
        is_active: bool | None = None,
    ) -> MailAliasData:
        """Update destinations, name, or active status of an existing alias."""

    @abc.abstractmethod
    def delete_alias(self, source: str) -> bool:
        """Delete an alias or distribution list. Return True if deleted, False if not found."""
