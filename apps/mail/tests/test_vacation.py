"""Unit tests for Sieve vacation auto-responder (RFC 5230, RFC 5260)."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.accounts.services.account import MailAccount
from apps.mail.models import UserSieveScript
from apps.mail.services.sieve_generator import (
    FilterAction,
    FilterCondition,
    FilterRule,
    VacationRule,
    compile_vacation_to_sieve,
    rules_to_sieve_script,
    sieve_script_to_rules,
    sieve_script_to_vacation,
)
from apps.mail.services.sieve_storage import (
    load_vacation_rule,
    save_sieve_rules,
    save_vacation_rule,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def mail_account() -> MailAccount:
    return MailAccount(
        email="vacationuser@example.com",
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
    return client


def test_compile_vacation_disabled():
    vacation = VacationRule(
        enabled=False,
        subject="Out of Office",
        message="I am on vacation",
    )
    code, caps = compile_vacation_to_sieve(vacation)
    assert "disabled" in code
    assert caps == set()


def test_compile_vacation_empty_message():
    vacation = VacationRule(
        enabled=True,
        subject="Out of Office",
        message="   ",
    )
    code, caps = compile_vacation_to_sieve(vacation)
    assert "disabled" in code
    assert caps == set()


def test_compile_vacation_without_dates():
    vacation = VacationRule(
        enabled=True,
        subject="Away from desk",
        message="Hello,\nI will reply soon.",
        days=3,
    )
    code, caps = compile_vacation_to_sieve(vacation)
    assert 'vacation :days 3 :subject "Away from desk"' in code
    assert "Hello,\nI will reply soon." in code
    assert caps == {"vacation"}
    assert "currentdate" not in code


def test_compile_vacation_with_both_dates():
    vacation = VacationRule(
        enabled=True,
        subject="On leave",
        message="Back next week.",
        days=7,
        start_date="2026-11-01",
        end_date="2026-11-15",
    )
    code, caps = compile_vacation_to_sieve(vacation)
    assert caps == {"vacation", "date", "relational"}
    assert 'currentdate :value "ge" "date" "2026-11-01"' in code
    assert 'currentdate :value "le" "date" "2026-11-15"' in code
    assert "allof (" in code
    assert 'vacation :days 7 :subject "On leave"' in code


def test_compile_vacation_with_single_date():
    vacation = VacationRule(
        enabled=True,
        subject="On leave",
        message="Back next week.",
        start_date="2026-11-01",
    )
    code, caps = compile_vacation_to_sieve(vacation)
    assert caps == {"vacation", "date", "relational"}
    assert 'currentdate :value "ge" "date" "2026-11-01"' in code
    assert "allof (" not in code


def test_compile_vacation_dot_stuffing():
    vacation = VacationRule(
        enabled=True,
        subject="Notice",
        message=".Dot at start of line\nNormal line\n..Double dot",
    )
    code, _caps = compile_vacation_to_sieve(vacation)
    assert "..Dot at start of line" in code
    assert "...Double dot" in code


def test_rules_to_sieve_script_combines_vacation_and_filters():
    rule = FilterRule(
        name="Archive Newsletters",
        active=True,
        conditions=[FilterCondition(field="from", comparator="contains", value="news@")],
        actions=[FilterAction(action_type="fileinto", argument="News")],
    )
    vacation = VacationRule(
        enabled=True,
        subject="Out of office",
        message="Away until Monday.",
        start_date="2026-11-01",
        end_date="2026-11-05",
    )
    script = rules_to_sieve_script([rule], vacation=vacation)

    # Check capabilities combined
    assert 'require ["date", "fileinto", "relational", "vacation"];' in script
    # Check both blocks present
    assert "vacation :days 7 :subject" in script
    assert 'header :contains "From" "news@"' in script

    # Check lossless round-trip
    parsed_rules = sieve_script_to_rules(script)
    assert len(parsed_rules) == 1
    assert parsed_rules[0].name == "Archive Newsletters"

    parsed_vacation = sieve_script_to_vacation(script)
    assert parsed_vacation is not None
    assert parsed_vacation.enabled is True
    assert parsed_vacation.subject == "Out of office"
    assert parsed_vacation.message == "Away until Monday."
    assert parsed_vacation.start_date == "2026-11-01"
    assert parsed_vacation.end_date == "2026-11-05"


def test_sieve_script_to_vacation_fallback_parser():
    raw_sieve = """
    require ["date", "relational", "vacation"];

    if allof (
        currentdate :value "ge" "date" "2026-12-01",
        currentdate :value "le" "date" "2026-12-25"
    ) {
        vacation :days 5 :subject "Holiday notice" text:
Happy holidays!
I will be back in January.
.
;
    }
    """
    vacation = sieve_script_to_vacation(raw_sieve)
    assert vacation is not None
    assert vacation.enabled is True
    assert vacation.days == 5
    assert vacation.subject == "Holiday notice"
    assert "Happy holidays!" in vacation.message
    assert vacation.start_date == "2026-12-01"
    assert vacation.end_date == "2026-12-25"


def test_load_and_save_vacation_rule_db_fallback(
    mail_account: MailAccount,
    monkeypatch: pytest.MonkeyPatch,
):
    rf = RequestFactory()
    request = rf.get("/")
    request.session = {}  # type: ignore[attr-defined]

    monkeypatch.setattr(
        "apps.mail.services.sieve_storage.get_account_managesieve_client",
        lambda r, a: None,
    )

    vacation, is_synced = load_vacation_rule(request, mail_account)
    assert vacation.enabled is False
    assert is_synced is False

    new_vacation = VacationRule(
        enabled=True,
        subject="Summer break",
        message="Enjoying the sun.",
        days=10,
        start_date="2026-07-01",
        end_date="2026-07-15",
    )
    synced = save_vacation_rule(request, mail_account, new_vacation)
    assert synced is False

    # Check persisted in DB
    record = cast(Any, UserSieveScript).objects.get(account_key=mail_account.account_key)
    assert record.rules_data["vacation"]["subject"] == "Summer break"
    assert record.is_active is True

    # Reload
    reloaded_vacation, reloaded_synced = load_vacation_rule(request, mail_account)
    assert reloaded_vacation.enabled is True
    assert reloaded_vacation.subject == "Summer break"
    assert reloaded_vacation.days == 10
    assert reloaded_synced is False


def test_save_sieve_rules_preserves_vacation_rule(
    mail_account: MailAccount,
    monkeypatch: pytest.MonkeyPatch,
):
    rf = RequestFactory()
    request = rf.get("/")
    request.session = {}  # type: ignore[attr-defined]

    monkeypatch.setattr(
        "apps.mail.services.sieve_storage.get_account_managesieve_client",
        lambda r, a: None,
    )

    # First save vacation
    vacation = VacationRule(
        enabled=True,
        subject="Conference trip",
        message="At PyCon.",
    )
    save_vacation_rule(request, mail_account, vacation)

    # Now save filter rules
    rule = FilterRule(name="Test Rule")
    save_sieve_rules(request, mail_account, [rule])

    # Ensure vacation is still intact
    reloaded_vacation, _ = load_vacation_rule(request, mail_account)
    assert reloaded_vacation.subject == "Conference trip"
    assert reloaded_vacation.enabled is True

    record = cast(Any, UserSieveScript).objects.get(account_key=mail_account.account_key)
    assert "At PyCon." in record.script_source


def test_save_vacation_syncs_with_managesieve_when_online(
    mail_account: MailAccount,
    monkeypatch: pytest.MonkeyPatch,
):
    rf = RequestFactory()
    request = rf.get("/")
    request.session = {}  # type: ignore[attr-defined]

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    monkeypatch.setattr(
        "apps.mail.services.sieve_storage.get_account_managesieve_client",
        lambda r, a: mock_client,
    )

    vacation = VacationRule(
        enabled=True,
        subject="Off-grid",
        message="Camping.",
    )
    is_synced = save_vacation_rule(request, mail_account, vacation)
    assert is_synced is True
    mock_client.put_script.assert_called_once()
    mock_client.set_active.assert_called_once()


def test_vacation_panel_view_get(logged_in_client: Client):
    url = reverse("mail:vacation_panel")
    response: Any = logged_in_client.get(url)
    assert response.status_code == 200
    assert "vacation-panel" in response.content.decode()


def test_vacation_save_view_post_success(logged_in_client: Client):
    url = reverse("mail:vacation_save")
    payload = {
        "enabled": "on",
        "subject": "Out of Office",
        "message": "I am traveling and will return soon.",
        "days": "5",
        "start_date": "2026-11-01",
        "end_date": "2026-11-10",
    }
    response: Any = logged_in_client.post(url, payload)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Out of Office" in content
    assert "I am traveling and will return soon." in content
    assert "alert-success" in content


def test_vacation_save_view_validation_error_empty_message(logged_in_client: Client):
    url = reverse("mail:vacation_save")
    payload = {
        "enabled": "on",
        "subject": "Out of Office",
        "message": "",
    }
    response: Any = logged_in_client.post(url, payload)
    assert response.status_code == 422
    content = response.content.decode()
    assert "alert-error" in content


def test_vacation_save_view_validation_error_date_order(logged_in_client: Client):
    url = reverse("mail:vacation_save")
    payload = {
        "enabled": "on",
        "subject": "Out of Office",
        "message": "Away.",
        "start_date": "2026-11-20",
        "end_date": "2026-11-10",
    }
    response: Any = logged_in_client.post(url, payload)
    assert response.status_code == 422
    content = response.content.decode()
    assert "alert-error" in content


def test_vacation_save_view_disable(logged_in_client: Client):
    url = reverse("mail:vacation_save")
    payload = {
        "subject": "Old Vacation",
        "message": "Past away message.",
    }
    response: Any = logged_in_client.post(url, payload)
    assert response.status_code == 200
    content = response.content.decode()
    assert "alert-success" in content
