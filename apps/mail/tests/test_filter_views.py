"""Tests for Sieve filter views and Carbonio-inspired management UI."""

from __future__ import annotations

from typing import Any, cast

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.services.account import MailAccount
from apps.mail.models import UserSieveScript


@pytest.fixture
def mail_account() -> MailAccount:
    return MailAccount(
        email="filteruser@example.com",
        domain="example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_security="ssl",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_security="starttls",
    )


@pytest.fixture
def logged_in_client(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    mail_account: MailAccount,
) -> Client:
    monkeypatch.setattr(
        "apps.accounts.middleware.load_mail_account",
        lambda request: mail_account,
    )
    monkeypatch.setattr(
        "apps.accounts.middleware.activate_session_language",
        lambda request: None,
    )
    monkeypatch.setattr(
        "apps.mail.views.load_mail_account",
        lambda request: mail_account,
    )
    monkeypatch.setattr(
        "apps.preferences.views.load_mail_account",
        lambda request: mail_account,
    )
    monkeypatch.setattr(
        "apps.mail.views.get_account_folder_choices",
        lambda request: [("INBOX", "Bandeja de entrada"), ("Archive", "Archivo")],
    )
    monkeypatch.setattr(
        "apps.mail.services.sieve_storage.get_account_managesieve_client",
        lambda request, account: None,
    )
    return client


@pytest.mark.django_db
def test_filters_panel_view_get(logged_in_client: Client, mail_account: MailAccount) -> None:
    # Seed a rule in DB fallback
    cast(Any, UserSieveScript).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
        name="djwebmail",
        rules_data={
            "incoming": [
                {
                    "id": "rule-1",
                    "name": "Facturas",
                    "active": True,
                    "conjunction": "anyof",
                    "conditions": [
                        {"field": "subject", "comparator": "contains", "value": "Factura"}
                    ],
                    "actions": [{"action_type": "fileinto", "argument": "Archive"}],
                    "stop": True,
                },
                {
                    "id": "rule-2",
                    "name": "Spam viejo",
                    "active": False,
                    "conjunction": "anyof",
                    "conditions": [{"field": "from", "comparator": "contains", "value": "promo@"}],
                    "actions": [{"action_type": "discard", "argument": ""}],
                    "stop": True,
                },
            ],
            "outgoing": [
                {
                    "id": "rule-out-1",
                    "name": "Copia Seguridad",
                    "active": True,
                    "conjunction": "anyof",
                    "conditions": [{"field": "to", "comparator": "contains", "value": "vip@"}],
                    "actions": [{"action_type": "redirect", "argument": "backup@example.com"}],
                    "stop": False,
                }
            ],
        },
    )

    url = reverse("mail:filters_panel")
    response: Any = logged_in_client.get(url)
    assert response.status_code == 200
    assert "Facturas" in response.content.decode()
    assert "Spam viejo" in response.content.decode()
    assert 'data-rule-column="active"' in response.content.decode()
    assert 'data-rule-column="available"' in response.content.decode()

    # Outgoing tab
    resp_out: Any = logged_in_client.get(url + "?tab=outgoing")
    assert resp_out.status_code == 200
    assert "Copia Seguridad" in resp_out.content.decode()


@pytest.mark.django_db
def test_filters_action_apply(logged_in_client: Client, mail_account: MailAccount) -> None:
    url = reverse("mail:filters_action")
    resp: Any = logged_in_client.post(url, {"tab": "incoming", "action": "apply"})
    assert resp.status_code == 200
    assert "filters-panel" in resp.content.decode()


@pytest.mark.django_db
def test_filter_save_edit_existing_rule(
    logged_in_client: Client,
    mail_account: MailAccount,
) -> None:
    cast(Any, UserSieveScript).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
        name="djwebmail",
        rules_data={
            "incoming": [
                {
                    "id": "existing-rule-id",
                    "name": "Nombre Anterior",
                    "active": True,
                    "conditions": [{"field": "subject", "comparator": "contains", "value": "Old"}],
                    "actions": [{"action_type": "keep", "argument": ""}],
                    "stop": True,
                }
            ],
            "outgoing": [],
        },
    )

    save_url = reverse("mail:filter_save")
    post_data = {
        "tab": "incoming",
        "rule_id": "existing-rule-id",
        "name": "Nombre Actualizado",
        "active": "on",
        "stop": "on",
        "conjunction": "allof",
        "condition_field[]": ["subject"],
        "condition_comparator[]": ["is"],
        "condition_value[]": ["Important Urgent"],
        "action_type[]": ["mark_starred"],
        "action_argument[]": [""],
    }
    resp: Any = logged_in_client.post(save_url, post_data)
    assert resp.status_code == 200
    assert "mail:filter-saved" in resp.headers.get("HX-Trigger", "")

    db_record: Any = cast(Any, UserSieveScript).objects.get(account_key=mail_account.account_key)
    rules = db_record.rules_data["incoming"]
    assert len(rules) == 1
    assert rules[0]["id"] == "existing-rule-id"
    assert rules[0]["name"] == "Nombre Actualizado"
    assert rules[0]["conjunction"] == "allof"
    assert rules[0]["conditions"][0]["value"] == "Important Urgent"
    assert rules[0]["actions"][0]["action_type"] == "mark_starred"


@pytest.mark.django_db
def test_filters_action_toggle_and_delete(
    logged_in_client: Client,
    mail_account: MailAccount,
) -> None:
    cast(Any, UserSieveScript).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
        name="djwebmail",
        rules_data={
            "incoming": [
                {
                    "id": "rule-1",
                    "name": "Filtro Uno",
                    "active": False,
                    "conditions": [{"field": "subject", "comparator": "contains", "value": "Test"}],
                    "actions": [{"action_type": "keep", "argument": ""}],
                }
            ],
            "outgoing": [],
        },
    )

    url = reverse("mail:filters_action")

    # 1. Add (activate)
    resp: Any = logged_in_client.post(
        url,
        {"tab": "incoming", "action": "add", "rule_id": "rule-1"},
    )
    assert resp.status_code == 200
    db_record: Any = cast(Any, UserSieveScript).objects.get(account_key=mail_account.account_key)
    assert db_record.rules_data["incoming"][0]["active"] is True

    # 2. Remove (deactivate)
    resp = logged_in_client.post(url, {"tab": "incoming", "action": "remove", "rule_id": "rule-1"})
    assert resp.status_code == 200
    db_record.refresh_from_db()
    assert db_record.rules_data["incoming"][0]["active"] is False

    # 3. Delete
    resp = logged_in_client.post(url, {"tab": "incoming", "action": "delete", "rule_id": "rule-1"})
    assert resp.status_code == 200
    db_record.refresh_from_db()
    assert len(db_record.rules_data["incoming"]) == 0


@pytest.mark.django_db
def test_filter_modal_create_and_edit(
    logged_in_client: Client,
    mail_account: MailAccount,
) -> None:
    cast(Any, UserSieveScript).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
        name="djwebmail",
        rules_data={
            "incoming": [
                {
                    "id": "rule-abc",
                    "name": "Avisos del Sistema",
                    "active": True,
                    "conjunction": "allof",
                    "conditions": [
                        {"field": "from", "comparator": "is", "value": "admin@example.com"}
                    ],
                    "actions": [{"action_type": "mark_starred", "argument": ""}],
                    "stop": True,
                }
            ],
            "outgoing": [],
        },
    )

    modal_url = reverse("mail:filter_modal")

    # Create modal
    resp_create: Any = logged_in_client.get(modal_url + "?tab=incoming")
    assert resp_create.status_code == 200
    content_create = resp_create.content.decode()
    assert "filter-modal" in content_create
    assert "tpl-condition-row" in content_create

    # Edit modal
    resp_edit: Any = logged_in_client.get(modal_url + "?tab=incoming&rule_id=rule-abc")
    assert resp_edit.status_code == 200
    content_edit = resp_edit.content.decode()
    assert "Avisos del Sistema" in content_edit
    assert "admin@example.com" in content_edit


@pytest.mark.django_db
def test_filter_save_validation_and_creation(
    logged_in_client: Client,
    mail_account: MailAccount,
) -> None:
    save_url = reverse("mail:filter_save")

    # 1. Missing name returns 422
    resp_fail: Any = logged_in_client.post(save_url, {"tab": "incoming", "name": ""})
    assert resp_fail.status_code == 422

    # 2. Valid new rule
    post_data = {
        "tab": "incoming",
        "name": "Facturación y Cobros",
        "active": "on",
        "stop": "on",
        "conjunction": "anyof",
        "condition_field[]": ["subject", "from"],
        "condition_comparator[]": ["contains", "ends_with"],
        "condition_value[]": ["Pago recibido", "@banco.com"],
        "action_type[]": ["fileinto", "mark_read"],
        "action_argument[]": ["Archive", ""],
    }
    resp_ok: Any = logged_in_client.post(save_url, post_data)
    assert resp_ok.status_code == 200
    assert "mail:filter-saved" in resp_ok.headers.get("HX-Trigger", "")

    db_record: Any = cast(Any, UserSieveScript).objects.get(account_key=mail_account.account_key)
    rules = db_record.rules_data["incoming"]
    assert len(rules) == 1
    assert rules[0]["name"] == "Facturación y Cobros"
    assert len(rules[0]["conditions"]) == 2
    assert len(rules[0]["actions"]) == 2
    assert rules[0]["actions"][0]["argument"] == "Archive"


@pytest.mark.django_db
def test_settings_index_includes_filters(
    logged_in_client: Client,
    mail_account: MailAccount,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.preferences.models import MailPreference

    cast(Any, MailPreference).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
    )
    monkeypatch.setattr(
        "apps.preferences.views.get_mail_preference",
        lambda request: cast(Any, MailPreference).objects.get(account_key=mail_account.account_key),
    )

    url = reverse("preferences:index") + "?section=filters"
    response: Any = logged_in_client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "section-filters" in content
    assert "filters-panel" in content
    assert 'value="filters"' in content
