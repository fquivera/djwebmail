"""Resolve a deployment mail account from settings and validate addresses."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.accounts.constants import (
    IMAP_SECURITY_VALUES,
    SMTP_SECURITY_VALUES,
)
from apps.accounts.exceptions import (
    MailAddressError,
    MailConfigurationError,
    MailDomainError,
)


@dataclass(frozen=True)
class MailAccount:
    """Connection settings for one deployment's IMAP/SMTP server."""

    email: str
    domain: str
    imap_host: str
    imap_port: int
    imap_security: str
    smtp_host: str
    smtp_port: int
    smtp_security: str
    verify_tls: bool = True
    timeout: int = 30

    def __post_init__(self) -> None:
        if self.imap_security not in IMAP_SECURITY_VALUES:
            raise MailConfigurationError("Unsupported IMAP security mode")
        if self.smtp_security not in SMTP_SECURITY_VALUES:
            raise MailConfigurationError("Unsupported SMTP security mode")
        if not 1 <= self.imap_port <= 65535 or not 1 <= self.smtp_port <= 65535:
            raise MailConfigurationError("Mail port is outside the valid range")
        if self.timeout <= 0:
            raise MailConfigurationError("Mail timeout must be positive")

    @property
    def account_key(self) -> str:
        """Stable opaque key used by preferences and identities."""
        return account_key(self.email, self.domain)


def account_key(email: str, domain: str) -> str:
    """Return the stable account identifier used instead of a Django user FK."""
    normalized = f"{email.strip().lower()}|{domain.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    """Validate and normalize an email address for IMAP login."""
    normalized = email.strip()
    try:
        validate_email(normalized)
    except ValidationError as exc:
        raise MailAddressError("Enter a valid email address") from exc
    return normalized.lower()


def resolve_mail_account(email: str) -> MailAccount:
    """Build the mail account for ``email`` from deployment settings.

    The deployment owns one mail domain. When ``DJANGO_MAIL_DOMAIN`` is set,
    addresses outside that domain are rejected before any IMAP connection is
    attempted.
    """
    normalized = normalize_email(email)
    email_domain = normalized.rsplit("@", 1)[1]
    configured_domain = settings.MAIL_DOMAIN.strip().lower()
    if configured_domain and email_domain != configured_domain:
        raise MailDomainError("The email domain is not served by this deployment")

    imap_host = settings.MAIL_IMAP_HOST.strip()
    if not imap_host:
        raise MailConfigurationError("DJANGO_MAIL_IMAP_HOST is not configured")

    return MailAccount(
        email=normalized,
        domain=configured_domain or email_domain,
        imap_host=imap_host,
        imap_port=settings.MAIL_IMAP_PORT,
        imap_security=settings.MAIL_IMAP_SECURITY,
        smtp_host=settings.MAIL_SMTP_HOST.strip(),
        smtp_port=settings.MAIL_SMTP_PORT,
        smtp_security=settings.MAIL_SMTP_SECURITY,
        verify_tls=settings.MAIL_VERIFY_TLS,
        timeout=settings.MAIL_TIMEOUT_SECONDS,
    )
