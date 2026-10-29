"""Unit tests for Sieve storage service (ManageSieve vs Database fallback)."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from django.test import RequestFactory

from apps.accounts.services.account import MailAccount
from apps.mail.models import UserSieveScript
from apps.mail.services.sieve_generator import FilterAction, FilterCondition, FilterRule
from apps.mail.services.sieve_storage import load_sieve_rules, save_sieve_rules

pytestmark = pytest.mark.django_db


@pytest.fixture
def account() -> MailAccount:
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
def request_with_session(rf: RequestFactory):
    request = rf.get("/")
    request.session = {}  # type: ignore[attr-defined]
    return request


def test_load_and_save_rules_fallback_to_database_when_managesieve_offline(
    request_with_session,
    account: MailAccount,
    monkeypatch: pytest.MonkeyPatch,
):
    # Ensure ManageSieve is reported as offline / unavailable
    monkeypatch.setattr(
        "apps.mail.services.sieve_storage.get_account_managesieve_client",
        lambda r, a: None,
    )

    # Initial load returns empty lists and server_synced = False
    incoming, outgoing, synced = load_sieve_rules(request_with_session, account)
    assert incoming == []
    assert outgoing == []
    assert synced is False

    rule = FilterRule(
        name="Move to Newsletters",
        active=True,
        conditions=[FilterCondition(field="from", comparator="contains", value="newsletter@")],
        actions=[FilterAction(action_type="fileinto", argument="Newsletters")],
        stop=True,
    )

    # Save rule in database fallback
    is_server_synced = save_sieve_rules(request_with_session, account, [rule])
    assert is_server_synced is False

    # Check database record was persisted
    record = cast(Any, UserSieveScript).objects.get(account_key=account.account_key)
    assert record.email == "filteruser@example.com"
    assert record.is_active is True
    assert 'fileinto "Newsletters"' in record.script_source

    # Reload rules
    reloaded_in, reloaded_out, reloaded_synced = load_sieve_rules(request_with_session, account)
    assert len(reloaded_in) == 1
    assert reloaded_in[0].name == "Move to Newsletters"
    assert reloaded_synced is False


def test_save_rules_syncs_to_managesieve_when_online(
    request_with_session,
    account: MailAccount,
    monkeypatch: pytest.MonkeyPatch,
):
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client

    monkeypatch.setattr(
        "apps.mail.services.sieve_storage.get_account_managesieve_client",
        lambda r, a: mock_client,
    )

    rule = FilterRule(
        name="Urgent to VIP",
        active=True,
        conditions=[FilterCondition(field="subject", value="Urgent")],
        actions=[FilterAction(action_type="fileinto", argument="VIP")],
    )

    is_server_synced = save_sieve_rules(request_with_session, account, [rule])
    assert is_server_synced is True

    mock_client.put_script.assert_called_once()
    assert mock_client.put_script.call_args[0][0] == "djwebmail"
    assert 'fileinto "VIP"' in mock_client.put_script.call_args[0][1]
    mock_client.set_active.assert_called_once_with("djwebmail")
