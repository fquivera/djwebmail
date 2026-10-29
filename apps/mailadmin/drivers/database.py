"""Database-backed mail account storage driver using Django ManagedMailbox."""

from __future__ import annotations

from django.db import DatabaseError, OperationalError, ProgrammingError
from django.utils.translation import gettext as _

from apps.accounts.services.password import hash_sha512_crypt
from apps.mailadmin.drivers.base import BaseMailAccountDriver, MailAccountData
from apps.mailadmin.exceptions import (
    MailAccountAlreadyExistsError,
    MailAccountNotFoundError,
    MailAdminError,
)
from apps.mailadmin.models import ManagedMailbox


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
