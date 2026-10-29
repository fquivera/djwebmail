"""Models for the mail app."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.constants import ACCOUNT_KEY_MAX_LENGTH


class UserSieveScript(models.Model):
    """Stores user Sieve filter scripts and structured rules in database fallback mode.

    When Dovecot Pigeonhole / ManageSieve is available on the server, filters are
    synchronized directly with the MDA. When unavailable, this model stores the
    active and draft filtering rules per mailbox account.
    """

    account_key = cast(
        str,
        models.CharField(max_length=ACCOUNT_KEY_MAX_LENGTH, db_index=True),
    )
    email = cast(str, models.EmailField(db_index=True))
    name = cast(str, models.CharField(max_length=128, default="djwebmail"))
    script_source = cast(str, models.TextField(blank=True, default=""))
    rules_data = cast(dict[str, Any], models.JSONField(default=dict, blank=True))
    is_active = cast(
        bool,
        models.BooleanField(default=True),  # pyright: ignore[reportArgumentType]
    )
    created_at = cast(datetime, models.DateTimeField(auto_now_add=True))
    updated_at = cast(datetime, models.DateTimeField(auto_now=True))

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = _("user sieve script")
        verbose_name_plural = _("user sieve scripts")
        constraints = [
            models.UniqueConstraint(
                fields=["account_key", "name"],
                name="unique_user_sieve_script_name",
            )
        ]

    def __str__(self) -> str:
        return f"{self.email} - {self.name} ({'active' if self.is_active else 'inactive'})"
