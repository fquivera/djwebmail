"""Tests for mail accounts administration views."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.services.account import MailAccount
from apps.mailadmin.drivers import get_account_driver
from apps.mailadmin.models import ManagedMailbox

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_account() -> MailAccount:
    return MailAccount(
        email="admin@example.com",
        domain="example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_security="ssl",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_security="starttls",
    )


@pytest.fixture
def regular_account() -> MailAccount:
    return MailAccount(
        email="user@example.com",
        domain="example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_security="ssl",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_security="starttls",
    )


@pytest.fixture
def admin_client(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    admin_account: MailAccount,
) -> Client:
    monkeypatch.setattr(
        "apps.accounts.middleware.load_mail_account",
        lambda request: admin_account,
    )
    monkeypatch.setattr(
        "apps.accounts.middleware.activate_session_timezone",
        lambda request: None,
    )
    session = client.session
    session["mail_email"] = admin_account.email
    session.save()
    return client


@pytest.fixture
def regular_client(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    regular_account: MailAccount,
) -> Client:
    monkeypatch.setattr(
        "apps.accounts.middleware.load_mail_account",
        lambda request: regular_account,
    )
    monkeypatch.setattr(
        "apps.accounts.middleware.activate_session_timezone",
        lambda request: None,
    )
    session = client.session
    session["mail_email"] = regular_account.email
    session.save()
    return client


@pytest.fixture(autouse=True)
def setup_admin_settings(settings: Any) -> None:
    settings.MAIL_ADMIN_ACCOUNTS = ["admin@example.com"]


class TestAccountListView:
    """Test suite for AccountListView."""

    def test_permission_denied_for_regular_user(self, regular_client: Client) -> None:
        response: Any = regular_client.get(reverse("mailadmin:accounts"))
        assert response.status_code == 403

    def test_list_accounts_accessible_for_admin(self, admin_client: Client) -> None:
        driver = get_account_driver()
        driver.create_account("mailbox1@example.com", "SecurePass123!")
        driver.create_account("mailbox2@example.com", "SecurePass123!", is_active=False)

        response: Any = admin_client.get(reverse("mailadmin:accounts"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "mailbox1@example.com" in content
        assert "mailbox2@example.com" in content

    def test_list_accounts_htmx_partial(self, admin_client: Client) -> None:
        driver = get_account_driver()
        driver.create_account("htmx_user@example.com", "SecurePass123!")

        response: Any = admin_client.get(
            reverse("mailadmin:accounts"),
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "htmx_user@example.com" in content
        # Check it is a partial without full html tag
        assert "<!doctype html>" not in content

    def test_list_accounts_search_and_status_filter(self, admin_client: Client) -> None:
        driver = get_account_driver()
        driver.create_account("alpha@example.com", "SecurePass123!", is_active=True)
        driver.create_account("beta@example.com", "SecurePass123!", is_active=False)

        # Filter active
        res_active: Any = admin_client.get(reverse("mailadmin:accounts") + "?status=active")
        assert "alpha@example.com" in res_active.content.decode("utf-8")
        assert "beta@example.com" not in res_active.content.decode("utf-8")

        # Search
        res_search: Any = admin_client.get(reverse("mailadmin:accounts") + "?q=beta")
        assert "beta@example.com" in res_search.content.decode("utf-8")
        assert "alpha@example.com" not in res_search.content.decode("utf-8")


class TestAccountCreateView:
    """Test suite for AccountCreateView."""

    def test_get_create_form(self, admin_client: Client) -> None:
        response: Any = admin_client.get(reverse("mailadmin:account_create"))
        assert response.status_code == 200
        assert "Create New Mail Account" in response.content.decode("utf-8")

    def test_create_account_success(self, admin_client: Client) -> None:
        payload = {
            "email": "newuser@example.com",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
            "quota_amount": "5",
            "quota_unit": "GB",
            "is_active": "on",
        }
        response: Any = admin_client.post(reverse("mailadmin:account_create"), data=payload)
        assert response.status_code == 302
        assert response.headers["Location"] == reverse("mailadmin:accounts")

        mb = ManagedMailbox.objects.get(email="newuser@example.com")
        assert mb.is_active is True
        assert mb.quota_bytes == 5 * 1024 * 1024 * 1024

    def test_create_account_validation_error_htmx_status_422(self, admin_client: Client) -> None:
        # Passwords don't match
        payload = {
            "email": "baduser@example.com",
            "password": "SecurePassword123!",
            "confirm_password": "DifferentPassword123!",
            "quota_unit": "UNLIMITED",
        }
        response: Any = admin_client.post(
            reverse("mailadmin:account_create"),
            data=payload,
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 422
        assert "Passwords do not match." in response.content.decode("utf-8")


class TestAccountEditView:
    """Test suite for AccountEditView."""

    def test_get_edit_form_existing_account(self, admin_client: Client) -> None:
        driver = get_account_driver()
        driver.create_account(
            "editable@example.com",
            "SecurePass123!",
            quota_bytes=2 * 1024 * 1024 * 1024,
        )

        response: Any = admin_client.get(
            reverse("mailadmin:account_edit", kwargs={"email": "editable@example.com"})
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "editable@example.com" in content

    def test_edit_account_updates_quota_and_status(self, admin_client: Client) -> None:
        driver = get_account_driver()
        driver.create_account("edit_me@example.com", "SecurePass123!", is_active=True)

        payload = {
            "password": "",
            "confirm_password": "",
            "quota_amount": "500",
            "quota_unit": "MB",
            # is_active unchecked
        }
        response: Any = admin_client.post(
            reverse("mailadmin:account_edit", kwargs={"email": "edit_me@example.com"}),
            data=payload,
        )
        assert response.status_code == 302

        mb = ManagedMailbox.objects.get(email="edit_me@example.com")
        assert mb.is_active is False
        assert mb.quota_bytes == 500 * 1024 * 1024

    def test_edit_non_existent_account_returns_404(self, admin_client: Client) -> None:
        response: Any = admin_client.get(
            reverse("mailadmin:account_edit", kwargs={"email": "ghost@example.com"})
        )
        assert response.status_code == 404


class TestAccountToggleAndDeleteViews:
    """Test suite for toggle status and delete views."""

    def test_toggle_account_status(self, admin_client: Client) -> None:
        driver = get_account_driver()
        driver.create_account("toggle@example.com", "SecurePass123!", is_active=True)

        # Toggle to suspended
        res1: Any = admin_client.post(
            reverse("mailadmin:account_toggle", kwargs={"email": "toggle@example.com"})
        )
        assert res1.status_code == 302
        acc1 = driver.get_account("toggle@example.com")
        assert acc1 is not None and acc1.is_active is False

        # Toggle to active
        res2: Any = admin_client.post(
            reverse("mailadmin:account_toggle", kwargs={"email": "toggle@example.com"})
        )
        assert res2.status_code == 302
        acc2 = driver.get_account("toggle@example.com")
        assert acc2 is not None and acc2.is_active is True

    def test_delete_account_success(self, admin_client: Client) -> None:
        driver = get_account_driver()
        driver.create_account("trash@example.com", "SecurePass123!")

        res: Any = admin_client.post(
            reverse("mailadmin:account_delete", kwargs={"email": "trash@example.com"})
        )
        assert res.status_code == 302
        assert driver.get_account("trash@example.com") is None
