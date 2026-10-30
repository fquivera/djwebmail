"""Tests for virtual aliases and distribution lists management."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.services.account import MailAccount
from apps.mailadmin.drivers.database import DatabaseMailAccountDriver
from apps.mailadmin.drivers.file import FileMailAccountDriver
from apps.mailadmin.exceptions import (
    MailAliasAlreadyExistsError,
)
from apps.mailadmin.forms import AliasCreateForm
from apps.mailadmin.models import ManagedAlias

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
    settings.MAIL_ADMIN_DRIVER = "database"


class TestManagedAliasModel:
    """Test suite for ManagedAlias model methods and properties."""

    def test_single_alias_properties(self) -> None:
        alias = ManagedAlias.objects.create(
            source="info@example.com",
            destinations="recipient@example.com",
            name="General Info",
            is_active=True,
        )
        assert str(alias) == "info@example.com (General Info)"
        assert alias.domain == "example.com"
        assert alias.get_destinations_list() == ["recipient@example.com"]
        assert alias.destination_count == 1
        assert not alias.is_distribution_list
        assert alias.destinations_display == "recipient@example.com"

    def test_distribution_list_properties(self) -> None:
        alias = ManagedAlias.objects.create(
            source="board@example.com",
            destinations="pres@example.com,\nvice@example.com;\ntres@example.com",
            name="Board of Directors",
            is_active=False,
        )
        assert alias.destination_count == 3
        assert alias.is_distribution_list
        assert alias.get_destinations_list() == [
            "pres@example.com",
            "vice@example.com",
            "tres@example.com",
        ]
        assert "pres@example.com, vice@example.com, tres@example.com" == alias.destinations_display


class TestDatabaseMailAccountDriverAliases:
    """Test suite for DatabaseMailAccountDriver virtual aliases methods."""

    def test_create_and_get_alias(self) -> None:
        driver = DatabaseMailAccountDriver()
        created = driver.create_alias(
            source="support@example.com",
            destinations=["tech@example.com", "help@example.com"],
            name="Customer Support",
            is_active=True,
        )
        assert created.source == "support@example.com"
        assert created.is_distribution_list
        assert created.destination_count == 2
        assert created.is_active

        fetched = driver.get_alias("support@example.com")
        assert fetched is not None
        assert fetched.source == "support@example.com"
        assert fetched.name == "Customer Support"

    def test_create_duplicate_alias_raises_error(self) -> None:
        driver = DatabaseMailAccountDriver()
        driver.create_alias("sales@example.com", ["sales1@example.com"])
        with pytest.raises(MailAliasAlreadyExistsError):
            driver.create_alias("sales@example.com", ["sales2@example.com"])

    def test_list_aliases_filtering(self) -> None:
        driver = DatabaseMailAccountDriver()
        driver.create_alias("team@example.com", ["u1@example.com", "u2@example.com"], name="Team")
        driver.create_alias("ceo@example.com", ["boss@example.com"], name="Chief", is_active=False)

        all_aliases = driver.list_aliases()
        assert len(all_aliases) == 2

        active_only = driver.list_aliases(is_active=True)
        assert len(active_only) == 1
        assert active_only[0].source == "team@example.com"

        inactive_only = driver.list_aliases(is_active=False)
        assert len(inactive_only) == 1
        assert inactive_only[0].source == "ceo@example.com"

        searched = driver.list_aliases(search="Team")
        assert len(searched) == 1
        assert searched[0].source == "team@example.com"

    def test_update_alias(self) -> None:
        driver = DatabaseMailAccountDriver()
        driver.create_alias("marketing@example.com", ["m1@example.com"])
        updated = driver.update_alias(
            "marketing@example.com",
            destinations=["m1@example.com", "m2@example.com"],
            name="Marketing Group",
            is_active=False,
        )
        assert updated.is_distribution_list
        assert updated.destination_count == 2
        assert updated.name == "Marketing Group"
        assert not updated.is_active

    def test_delete_alias(self) -> None:
        driver = DatabaseMailAccountDriver()
        driver.create_alias("temp@example.com", ["user@example.com"])
        assert driver.delete_alias("temp@example.com")
        assert driver.get_alias("temp@example.com") is None
        assert not driver.delete_alias("nonexistent@example.com")


class TestFileMailAccountDriverAliases:
    """Test suite for FileMailAccountDriver virtual aliases methods with postfix-virtual.cf."""

    def test_file_driver_lifecycle(self, tmp_path: Any) -> None:
        accounts_file = str(tmp_path / "postfix-accounts.cf")
        virtual_file = str(tmp_path / "postfix-virtual.cf")
        driver = FileMailAccountDriver(
            accounts_file=accounts_file,
            virtual_file=virtual_file,
        )

        # Create alias
        alias = driver.create_alias(
            source="contact@example.com",
            destinations=["admin@example.com", "desk@example.com"],
            name="",
            is_active=True,
        )
        assert alias.source == "contact@example.com"
        assert alias.is_distribution_list

        # Verify on disk
        with open(virtual_file, encoding="utf-8") as f:
            content = f.read()
        assert "contact@example.com admin@example.com desk@example.com" in content

        # Update to suspended
        updated = driver.update_alias("contact@example.com", is_active=False)
        assert not updated.is_active
        with open(virtual_file, encoding="utf-8") as f:
            content = f.read()
        assert "# contact@example.com admin@example.com desk@example.com" in content

        # Read back with list_aliases
        aliases = driver.list_aliases()
        assert len(aliases) == 1
        assert not aliases[0].is_active

        # Delete alias
        assert driver.delete_alias("contact@example.com")
        assert len(driver.list_aliases()) == 0


class TestAliasForms:
    """Test suite for AliasCreateForm and AliasEditForm."""

    def test_create_form_valid(self) -> None:
        form = AliasCreateForm(
            data={
                "source": "billing@example.com",
                "name": "Finance & Billing",
                "destinations": "acc1@example.com\nacc2@example.com",
                "is_active": True,
            }
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["source"] == "billing@example.com"
        assert len(form.cleaned_data["destinations"]) == 2

    def test_create_form_self_loop_error(self) -> None:
        form = AliasCreateForm(
            data={
                "source": "loop@example.com",
                "destinations": "loop@example.com\nother@example.com",
                "is_active": True,
            }
        )
        assert not form.is_valid()
        assert form.has_error("destinations")

    def test_create_form_invalid_email_in_destinations(self) -> None:
        form = AliasCreateForm(
            data={
                "source": "valid@example.com",
                "destinations": "good@example.com\nnot-an-email",
                "is_active": True,
            }
        )
        assert not form.is_valid()
        assert form.has_error("destinations")

    def test_create_form_duplicate_source(self) -> None:
        ManagedAlias.objects.create(
            source="existing@example.com",
            destinations="dest@example.com",
        )
        form = AliasCreateForm(
            data={
                "source": "existing@example.com",
                "destinations": "other@example.com",
                "is_active": True,
            }
        )
        assert not form.is_valid()
        assert form.has_error("source")


class TestAliasViews:
    """Test suite for Alias admin views."""

    def test_aliases_list_forbidden_for_regular_user(self, regular_client: Client) -> None:
        response: Any = regular_client.get(reverse("mailadmin:aliases"))
        assert response.status_code == 403

    def test_aliases_list_accessible_for_admin(self, admin_client: Client) -> None:
        ManagedAlias.objects.create(
            source="dev@example.com",
            destinations="dev1@example.com, dev2@example.com",
            name="Developers",
            is_active=True,
        )
        response: Any = admin_client.get(reverse("mailadmin:aliases"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "dev@example.com" in content
        assert "Developers" in content
        assert "Distribution List" in content

    def test_aliases_list_htmx_partial(self, admin_client: Client) -> None:
        ManagedAlias.objects.create(
            source="htmx@example.com",
            destinations="target@example.com",
            name="HTMX Alias",
            is_active=True,
        )
        response: Any = admin_client.get(
            reverse("mailadmin:aliases"),
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "htmx@example.com" in content
        assert "<html" not in content

    def test_alias_create_get_and_post_valid(self, admin_client: Client) -> None:
        get_resp: Any = admin_client.get(reverse("mailadmin:alias_create"))
        assert get_resp.status_code == 200

        post_data = {
            "source": "created@example.com",
            "name": "New Alias",
            "destinations": "target1@example.com\ntarget2@example.com",
            "is_active": True,
        }
        post_resp: Any = admin_client.post(reverse("mailadmin:alias_create"), post_data)
        assert post_resp.status_code == 302
        assert ManagedAlias.objects.filter(source="created@example.com").exists()

    def test_alias_create_htmx_redirect(self, admin_client: Client) -> None:
        post_data = {
            "source": "htmx_alias@example.com",
            "name": "HTMX Alias",
            "destinations": "target@example.com",
            "is_active": True,
        }
        post_resp: Any = admin_client.post(
            reverse("mailadmin:alias_create"),
            post_data,
            HTTP_HX_REQUEST="true",
        )
        assert post_resp.status_code == 200
        assert post_resp.headers.get("HX-Redirect") == reverse("mailadmin:aliases")

    def test_alias_create_invalid_returns_422(self, admin_client: Client) -> None:
        post_resp: Any = admin_client.post(
            reverse("mailadmin:alias_create"),
            {"source": "", "destinations": ""},
        )
        assert post_resp.status_code == 422

    def test_alias_edit_get_and_post(self, admin_client: Client) -> None:
        ManagedAlias.objects.create(
            source="to_edit@example.com",
            destinations="initial@example.com",
            name="Initial Name",
            is_active=True,
        )
        edit_url = reverse("mailadmin:alias_edit", kwargs={"source": "to_edit@example.com"})
        get_resp: Any = admin_client.get(edit_url)
        assert get_resp.status_code == 200

        post_resp: Any = admin_client.post(
            edit_url,
            {
                "name": "Updated Name",
                "destinations": "updated1@example.com\nupdated2@example.com",
                "is_active": False,
            },
        )
        assert post_resp.status_code == 302
        alias = ManagedAlias.objects.get(source="to_edit@example.com")
        assert alias.name == "Updated Name"
        assert not alias.is_active
        assert alias.destination_count == 2

    def test_alias_toggle_status(self, admin_client: Client) -> None:
        ManagedAlias.objects.create(
            source="toggle@example.com",
            destinations="target@example.com",
            is_active=True,
        )
        toggle_url = reverse("mailadmin:alias_toggle", kwargs={"source": "toggle@example.com"})
        post_resp: Any = admin_client.post(toggle_url)
        assert post_resp.status_code == 302
        alias = ManagedAlias.objects.get(source="toggle@example.com")
        assert not alias.is_active

        # Toggle again
        admin_client.post(toggle_url)
        alias.refresh_from_db()
        assert alias.is_active

    def test_alias_delete(self, admin_client: Client) -> None:
        ManagedAlias.objects.create(
            source="to_delete@example.com",
            destinations="target@example.com",
        )
        delete_url = reverse("mailadmin:alias_delete", kwargs={"source": "to_delete@example.com"})
        post_resp: Any = admin_client.post(delete_url)
        assert post_resp.status_code == 302
        assert not ManagedAlias.objects.filter(source="to_delete@example.com").exists()
