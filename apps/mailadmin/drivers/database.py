"""Database-backed mail account storage driver using Django ManagedMailbox."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from django.db import DatabaseError, OperationalError, ProgrammingError
from django.db.models import Q
from django.utils.translation import gettext as _

from apps.accounts.services.password import hash_sha512_crypt
from apps.mailadmin.drivers.base import BaseMailAccountDriver, MailAccountData, MailAliasData
from apps.mailadmin.exceptions import (
    MailAccountAlreadyExistsError,
    MailAccountNotFoundError,
    MailAdminError,
    MailAliasAlreadyExistsError,
    MailAliasNotFoundError,
)
from apps.mailadmin.models import ManagedAlias, ManagedMailbox


class DatabaseMailAccountDriver(BaseMailAccountDriver):
    """Driver managing mail accounts directly in the DjWebmail database."""

    def _to_data(self, mailbox: ManagedMailbox) -> MailAccountData:
        return MailAccountData(
            email=mailbox.email,
            is_active=mailbox.is_active,
            quota_bytes=mailbox.quota_bytes,
            created_at=mailbox.created_at,
            updated_at=mailbox.updated_at,
        )

    def list_accounts(
        self,
        search: str = "",
        is_active: bool | None = None,
    ) -> list[MailAccountData]:
        try:
            qs = ManagedMailbox.objects.all().order_by("email")
            if search.strip():
                qs = qs.filter(email__icontains=search.strip())
            if is_active is not None:
                qs = qs.filter(is_active=is_active)
            return [self._to_data(mb) for mb in qs]
        except (DatabaseError, ProgrammingError, OperationalError) as exc:
            raise MailAdminError(
                _("Database error querying mail accounts: %(error)s") % {"error": str(exc)}
            ) from exc

    def get_account(self, email: str) -> MailAccountData | None:
        try:
            target_email = email.strip().lower()
            mailbox = ManagedMailbox.objects.filter(email__iexact=target_email).first()
            if not mailbox:
                return None
            return self._to_data(mailbox)
        except (DatabaseError, ProgrammingError, OperationalError) as exc:
            raise MailAdminError(
                _("Database error retrieving mail account: %(error)s") % {"error": str(exc)}
            ) from exc

    def create_account(
        self,
        email: str,
        password: str,
        quota_bytes: int | None = None,
        is_active: bool = True,
    ) -> MailAccountData:
        target_email = email.strip().lower()
        if self.get_account(target_email) is not None:
            raise MailAccountAlreadyExistsError(
                _("An account with email '%(email)s' already exists.") % {"email": target_email}
            )

        password_hash = hash_sha512_crypt(password)
        try:
            mailbox = ManagedMailbox.objects.create(
                email=target_email,
                password_hash=password_hash,
                quota_bytes=quota_bytes,
                is_active=is_active,
            )
            return self._to_data(mailbox)
        except (DatabaseError, ProgrammingError, OperationalError) as exc:
            raise MailAdminError(
                _("Failed to create mail account in database: %(error)s") % {"error": str(exc)}
            ) from exc

    def update_account(
        self,
        email: str,
        password: str | None = None,
        quota_bytes: int | None = None,
        is_active: bool | None = None,
        clear_quota: bool = False,
    ) -> MailAccountData:
        target_email = email.strip().lower()
        try:
            mailbox = ManagedMailbox.objects.filter(email__iexact=target_email).first()
            if not mailbox:
                raise MailAccountNotFoundError(
                    _("Account '%(email)s' not found.") % {"email": target_email}
                )

            if password:
                mailbox.password_hash = hash_sha512_crypt(password)
            if clear_quota:
                mailbox.quota_bytes = None
            elif quota_bytes is not None:
                mailbox.quota_bytes = quota_bytes
            if is_active is not None:
                mailbox.is_active = is_active

            mailbox.save()
            return self._to_data(mailbox)
        except (DatabaseError, ProgrammingError, OperationalError) as exc:
            raise MailAdminError(
                _("Failed to update mail account: %(error)s") % {"error": str(exc)}
            ) from exc

    def delete_account(self, email: str) -> bool:
        target_email = email.strip().lower()
        try:
            deleted_count, _ = ManagedMailbox.objects.filter(email__iexact=target_email).delete()
            return bool(deleted_count > 0)
        except (DatabaseError, ProgrammingError, OperationalError) as exc:
            raise MailAdminError(
                _("Failed to delete mail account: %(error)s") % {"error": str(exc)}
            ) from exc

    def _alias_to_data(self, alias: ManagedAlias) -> MailAliasData:
        return MailAliasData(
            source=alias.source,
            destinations=alias.get_destinations_list(),
            name=alias.name,
            is_active=alias.is_active,
            created_at=alias.created_at,
            updated_at=alias.updated_at,
        )

    def list_aliases(
        self,
        search: str = "",
        is_active: bool | None = None,
    ) -> list[MailAliasData]:
        try:
            qs = cast(Any, ManagedAlias).objects.all().order_by("source")
            if search.strip():
                term = search.strip()
                qs = qs.filter(
                    cast(Any, Q(source__icontains=term))
                    | cast(Any, Q(destinations__icontains=term))
                    | cast(Any, Q(name__icontains=term))
                )
            if is_active is not None:
                qs = qs.filter(is_active=is_active)
            return [self._alias_to_data(a) for a in qs]
        except (DatabaseError, ProgrammingError, OperationalError) as exc:
            raise MailAdminError(
                _("Database error querying virtual aliases: %(error)s") % {"error": str(exc)}
            ) from exc

    def get_alias(self, source: str) -> MailAliasData | None:
        try:
            target = source.strip().lower()
            alias = cast(Any, ManagedAlias).objects.filter(source__iexact=target).first()
            if not alias:
                return None
            return self._alias_to_data(alias)
        except (DatabaseError, ProgrammingError, OperationalError) as exc:
            raise MailAdminError(
                _("Database error retrieving alias: %(error)s") % {"error": str(exc)}
            ) from exc

    def create_alias(
        self,
        source: str,
        destinations: Sequence[str],
        name: str = "",
        is_active: bool = True,
    ) -> MailAliasData:
        target = source.strip().lower()
        clean_dests = [d.strip().lower() for d in destinations if d.strip()]
        if not clean_dests:
            raise MailAdminError(_("An alias must have at least one destination address."))

        if self.get_alias(target) is not None:
            raise MailAliasAlreadyExistsError(
                _("An alias for '%(source)s' already exists.") % {"source": target}
            )

        try:
            alias = cast(Any, ManagedAlias).objects.create(
                source=target,
                destinations=",\n".join(clean_dests),
                name=name.strip(),
                is_active=is_active,
            )
            return self._alias_to_data(alias)
        except (DatabaseError, ProgrammingError, OperationalError) as exc:
            raise MailAdminError(
                _("Failed to create alias: %(error)s") % {"error": str(exc)}
            ) from exc

    def update_alias(
        self,
        source: str,
        destinations: Sequence[str] | None = None,
        name: str | None = None,
        is_active: bool | None = None,
    ) -> MailAliasData:
        target = source.strip().lower()
        try:
            alias = cast(Any, ManagedAlias).objects.filter(source__iexact=target).first()
            if not alias:
                raise MailAliasNotFoundError(
                    _("Alias '%(source)s' not found.") % {"source": target}
                )

            if destinations is not None:
                clean_dests = [d.strip().lower() for d in destinations if d.strip()]
                if not clean_dests:
                    raise MailAdminError(_("An alias must have at least one destination address."))
                alias.destinations = ",\n".join(clean_dests)

            if name is not None:
                alias.name = name.strip()
            if is_active is not None:
                alias.is_active = is_active

            alias.save()
            return self._alias_to_data(alias)
        except (DatabaseError, ProgrammingError, OperationalError) as exc:
            raise MailAdminError(
                _("Failed to update alias: %(error)s") % {"error": str(exc)}
            ) from exc

    def delete_alias(self, source: str) -> bool:
        target = source.strip().lower()
        try:
            deleted_count, _ = (
                cast(Any, ManagedAlias).objects.filter(source__iexact=target).delete()
            )
            return bool(deleted_count > 0)
        except (DatabaseError, ProgrammingError, OperationalError) as exc:
            raise MailAdminError(
                _("Failed to delete alias: %(error)s") % {"error": str(exc)}
            ) from exc
