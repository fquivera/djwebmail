"""Tests for mail account storage drivers (database and file)."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator

import pytest
from django.test import override_settings

from apps.mailadmin.drivers import (
    DatabaseMailAccountDriver,
    FileMailAccountDriver,
    format_storage_bytes,
    get_account_driver,
)
from apps.mailadmin.drivers.file import (
    format_bytes_to_quota_string,
    parse_quota_string_to_bytes,
)
from apps.mailadmin.exceptions import (
    MailAccountAlreadyExistsError,
    MailAccountNotFoundError,
)
from apps.mailadmin.models import ManagedMailbox


@pytest.fixture
def temp_accounts_file() -> Generator[str, None, None]:
    with tempfile.NamedTemporaryFile("w", suffix=".cf", delete=False) as f:
        f.write("# postfix-accounts.cf test\n")
        path = f.name
    yield path
    if os.path.exists(path):
        os.remove(path)
    quotas_file = os.path.join(os.path.dirname(path), "dovecot-quotas.cf")
    if os.path.exists(quotas_file):
        os.remove(quotas_file)


@pytest.mark.django_db
class TestDatabaseMailAccountDriver:
    """Test suite for DatabaseMailAccountDriver."""

    def test_create_and_get_account(self) -> None:
        driver = DatabaseMailAccountDriver()
        account = driver.create_account(
            email="user1@example.com",
            password="SecurePassword123!",
            quota_bytes=2 * 1024 * 1024 * 1024,
            is_active=True,
        )

        assert account.email == "user1@example.com"
        assert account.username == "user1"
        assert account.domain == "example.com"
        assert account.is_active is True
        assert account.quota_bytes == 2 * 1024 * 1024 * 1024
        assert account.quota_display == "2 GB"

        # Verify underlying model
        mb = ManagedMailbox.objects.get(email="user1@example.com")
        assert mb.password_hash.startswith("{SHA512-CRYPT}")
        assert mb.is_active is True

        # Fetch via driver
        fetched = driver.get_account("user1@example.com")
        assert fetched is not None
        assert fetched.email == "user1@example.com"

    def test_create_duplicate_email_raises_error(self) -> None:
        driver = DatabaseMailAccountDriver()
        driver.create_account("unique@example.com", "Password123!")

        with pytest.raises(MailAccountAlreadyExistsError):
            driver.create_account("unique@example.com", "AnotherPassword123!")

    def test_list_accounts_search_and_filter(self) -> None:
        driver = DatabaseMailAccountDriver()
        driver.create_account("alice@corp.com", "Password123!", is_active=True)
        driver.create_account("bob@corp.com", "Password123!", is_active=False)
        driver.create_account("carol@other.com", "Password123!", is_active=True)

        all_accounts = driver.list_accounts()
        assert len(all_accounts) == 3

        # Search filter
        corp_accounts = driver.list_accounts(search="corp.com")
        assert len(corp_accounts) == 2

        # Active filter
        active_accounts = driver.list_accounts(is_active=True)
        assert len(active_accounts) == 2
        assert "bob@corp.com" not in [a.email for a in active_accounts]

        inactive_accounts = driver.list_accounts(is_active=False)
        assert len(inactive_accounts) == 1
        assert inactive_accounts[0].email == "bob@corp.com"

    def test_update_account(self) -> None:
        driver = DatabaseMailAccountDriver()
        driver.create_account(
            "update@example.com",
            "InitialPass123!",
            quota_bytes=1024 * 1024 * 1024,
            is_active=True,
        )

        # Update quota and status
        updated = driver.update_account(
            "update@example.com",
            quota_bytes=5 * 1024 * 1024 * 1024,
            is_active=False,
        )
        assert updated.is_active is False
        assert updated.quota_bytes == 5 * 1024 * 1024 * 1024

        # Clear quota (unlimited)
        cleared = driver.update_account("update@example.com", clear_quota=True)
        assert cleared.quota_bytes is None
        assert cleared.quota_display == "Unlimited"

    def test_update_non_existent_account_raises_error(self) -> None:
        driver = DatabaseMailAccountDriver()
        with pytest.raises(MailAccountNotFoundError):
            driver.update_account("nonexistent@example.com", is_active=False)

    def test_delete_account(self) -> None:
        driver = DatabaseMailAccountDriver()
        driver.create_account("delete_me@example.com", "Password123!")

        assert driver.delete_account("delete_me@example.com") is True
        assert driver.get_account("delete_me@example.com") is None
        assert driver.delete_account("delete_me@example.com") is False


class TestFileMailAccountDriver:
    """Test suite for FileMailAccountDriver (docker-mailserver postfix-accounts format)."""

    def test_file_driver_crud_operations(self, temp_accounts_file: str) -> None:
        driver = FileMailAccountDriver(accounts_file=temp_accounts_file)

        # Create
        acc = driver.create_account(
            email="fileuser@example.test",
            password="SecurePass123!",
            quota_bytes=1024 * 1024 * 1024,
            is_active=True,
        )
        assert acc.email == "fileuser@example.test"
        assert acc.is_active is True
        assert acc.quota_bytes == 1024 * 1024 * 1024

        # Read back
        fetched = driver.get_account("fileuser@example.test")
        assert fetched is not None
        assert fetched.email == "fileuser@example.test"

        # Duplicate
        with pytest.raises(MailAccountAlreadyExistsError):
            driver.create_account("fileuser@example.test", "AnotherPass123!")

        # Update status to suspended
        updated = driver.update_account("fileuser@example.test", is_active=False)
        assert updated.is_active is False

        # Inactive filter
        inactive = driver.list_accounts(is_active=False)
        assert len(inactive) == 1
        assert inactive[0].email == "fileuser@example.test"

        # Reactivate and update quota
        updated2 = driver.update_account(
            "fileuser@example.test",
            is_active=True,
            quota_bytes=2 * 1024 * 1024 * 1024,
        )
        assert updated2.is_active is True
        assert updated2.quota_bytes == 2 * 1024 * 1024 * 1024

        # Delete
        assert driver.delete_account("fileuser@example.test") is True
        assert driver.get_account("fileuser@example.test") is None


def test_quota_helpers() -> None:
    assert parse_quota_string_to_bytes("2048M") == 2048 * 1024 * 1024
    assert parse_quota_string_to_bytes("5G") == 5 * 1024 * 1024 * 1024
    assert parse_quota_string_to_bytes("0") is None
    assert parse_quota_string_to_bytes("UNLIMITED") is None

    assert format_bytes_to_quota_string(2 * 1024 * 1024 * 1024) == "2G"
    assert format_bytes_to_quota_string(500 * 1024 * 1024) == "500M"
    assert format_bytes_to_quota_string(None) == ""

    assert format_storage_bytes(None) == "Unlimited"
    assert format_storage_bytes(1073741824) == "1 GB"
    assert format_storage_bytes(524288000) == "500 MB"


def test_driver_factory(temp_accounts_file: str) -> None:
    with override_settings(MAIL_ADMIN_DRIVER="database"):
        driver = get_account_driver()
        assert isinstance(driver, DatabaseMailAccountDriver)

    with override_settings(MAIL_ADMIN_DRIVER="file", MAIL_ACCOUNTS_FILE=temp_accounts_file):
        driver = get_account_driver()
        assert isinstance(driver, FileMailAccountDriver)

    with override_settings(MAIL_ADMIN_DRIVER="auto", MAIL_ACCOUNTS_FILE=temp_accounts_file):
        driver = get_account_driver()
        assert isinstance(driver, FileMailAccountDriver)

    with override_settings(MAIL_ADMIN_DRIVER="auto", MAIL_ACCOUNTS_FILE=""):
        driver = get_account_driver()
        assert isinstance(driver, DatabaseMailAccountDriver)
