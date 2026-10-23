"""Tests for deployment account resolution and stable account keys."""

import pytest
from django.test import override_settings

from apps.accounts.exceptions import (
    MailAddressError,
    MailConfigurationError,
    MailDomainError,
)
from apps.accounts.services.account import account_key, resolve_mail_account


@override_settings(
    MAIL_DOMAIN="example.com",
    MAIL_IMAP_HOST="imap.example.com",
    MAIL_IMAP_PORT=993,
    MAIL_IMAP_SECURITY="ssl",
    MAIL_SMTP_HOST="smtp.example.com",
    MAIL_SMTP_PORT=587,
    MAIL_SMTP_SECURITY="starttls",
    MAIL_VERIFY_TLS=True,
    MAIL_TIMEOUT_SECONDS=30,
)
def test_resolve_mail_account_from_settings():
    account = resolve_mail_account("  User@Example.COM ")

    assert account.email == "user@example.com"
    assert account.domain == "example.com"
    assert account.imap_host == "imap.example.com"
    assert account.imap_port == 993
    assert account.imap_security == "ssl"
    assert account.smtp_host == "smtp.example.com"
    assert account.smtp_security == "starttls"
    assert account.account_key == account_key("user@example.com", "example.com")


@override_settings(MAIL_DOMAIN="example.com", MAIL_IMAP_HOST="imap.example.com")
def test_resolve_rejects_other_domain():
    with pytest.raises(MailDomainError):
        resolve_mail_account("user@other.example")


@override_settings(MAIL_DOMAIN="", MAIL_IMAP_HOST="imap.example.com")
def test_resolve_uses_address_domain_when_not_configured():
    account = resolve_mail_account("user@example.com")

    assert account.domain == "example.com"


@override_settings(MAIL_DOMAIN="example.com", MAIL_IMAP_HOST="")
def test_resolve_requires_imap_host():
    with pytest.raises(MailConfigurationError):
        resolve_mail_account("user@example.com")


@override_settings(MAIL_DOMAIN="example.com", MAIL_IMAP_HOST="imap.example.com")
def test_resolve_rejects_invalid_email():
    with pytest.raises(MailAddressError):
        resolve_mail_account("not-an-email")


def test_account_key_is_stable_and_domain_scoped():
    first = account_key("User@Example.com", "example.com")
    second = account_key("user@example.com", "example.com")

    assert first == second
    assert len(first) == 64
    assert first != account_key("user@example.com", "other.example")
