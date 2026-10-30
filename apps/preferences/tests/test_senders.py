"""Unit tests for TrustedSender and BlockedSender models, services, and views."""

from __future__ import annotations

from typing import Any, cast

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.accounts.services.account import MailAccount
from apps.preferences.forms import BlockedSenderForm, TrustedSenderForm
from apps.preferences.models import BlockedSender, BlockedSenderAction, TrustedSender
from apps.preferences.services import (
    add_blocked_sender,
    add_trusted_sender,
    delete_blocked_sender,
    delete_trusted_sender,
    extract_sender_address_and_domain,
    get_blocked_senders,
    get_trusted_senders,
    is_sender_blocked,
    is_sender_trusted,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def mail_account() -> MailAccount:
    return MailAccount(
        email="testowner@example.com",
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
        "apps.preferences.views.load_mail_account",
        lambda request: mail_account,
    )
    return client


def test_extract_sender_address_and_domain():
    addr, dom = extract_sender_address_and_domain("John Doe <John@Example.COM>")
    assert addr == "john@example.com"
    assert dom == "example.com"

    addr2, dom2 = extract_sender_address_and_domain("support@service.net")
    assert addr2 == "support@service.net"
    assert dom2 == "service.net"


def test_trusted_sender_model_normalization_and_validation(mail_account: MailAccount):
    # Normalized leading @ stripped and lowercased
    sender = TrustedSender(
        account_key=mail_account.account_key,
        email=mail_account.email,
        pattern=" @NewsLetter.COM ",
    )
    sender.full_clean()
    sender.save()
    assert sender.pattern == "newsletter.com"
    assert "testowner@example.com -> newsletter.com" in str(sender)

    # Empty pattern raises ValidationError
    empty_sender = TrustedSender(
        account_key=mail_account.account_key,
        email=mail_account.email,
        pattern="   ",
    )
    with pytest.raises(ValidationError):
        empty_sender.full_clean()


def test_blocked_sender_model_normalization_and_action(mail_account: MailAccount):
    blocked = BlockedSender(
        account_key=mail_account.account_key,
        email=mail_account.email,
        pattern=" SPAMMER@EVIL.ORG ",
        action=BlockedSenderAction.DISCARD,
    )
    blocked.full_clean()
    blocked.save()
    assert blocked.pattern == "spammer@evil.org"
    assert blocked.action == BlockedSenderAction.DISCARD
    assert "discard" in str(blocked)


def test_is_sender_trusted_matching(mail_account: MailAccount):
    add_trusted_sender(
        account_key=mail_account.account_key,
        email=mail_account.email,
        pattern="github.com",
    )
    add_trusted_sender(
        account_key=mail_account.account_key,
        email=mail_account.email,
        pattern="friend@personal.org",
    )

    # Matches domain
    assert is_sender_trusted(
        mail_account.account_key,
        "GitHub Notifications <notifications@github.com>",
    )
    # Matches exact address
    assert is_sender_trusted(mail_account.account_key, "friend@personal.org")
    # Untrusted domain / address
    assert not is_sender_trusted(mail_account.account_key, "random@unknown.com")
    # Other account does not match
    assert not is_sender_trusted("other-account-key", "notifications@github.com")


def test_is_sender_blocked_matching(mail_account: MailAccount):
    add_blocked_sender(
        account_key=mail_account.account_key,
        email=mail_account.email,
        pattern="bad-domain.com",
        action=BlockedSenderAction.TRASH,
    )
    add_blocked_sender(
        account_key=mail_account.account_key,
        email=mail_account.email,
        pattern="pest@phishing.net",
        action=BlockedSenderAction.DISCARD,
    )

    match1 = is_sender_blocked(mail_account.account_key, "Sales <offer@bad-domain.com>")
    assert match1 is not None
    assert match1.action == BlockedSenderAction.TRASH

    match2 = is_sender_blocked(mail_account.account_key, "pest@phishing.net")
    assert match2 is not None
    assert match2.action == BlockedSenderAction.DISCARD

    assert is_sender_blocked(mail_account.account_key, "good@domain.com") is None


def test_crud_senders_services(mail_account: MailAccount):
    t1 = add_trusted_sender(mail_account.account_key, mail_account.email, "company.com", "Work")
    assert len(get_trusted_senders(mail_account.account_key)) == 1

    b1 = add_blocked_sender(
        mail_account.account_key,
        mail_account.email,
        "spam.com",
        description="Junk",
    )
    assert len(get_blocked_senders(mail_account.account_key)) == 1

    delete_trusted_sender(mail_account.account_key, cast(int, t1.pk))
    assert len(get_trusted_senders(mail_account.account_key)) == 0

    delete_blocked_sender(mail_account.account_key, cast(int, b1.pk))
    assert len(get_blocked_senders(mail_account.account_key)) == 0


def test_forms_validation():
    t_form = TrustedSenderForm(data={"pattern": " @trusted.net ", "description": "Good"})
    assert t_form.is_valid()
    assert t_form.cleaned_data["pattern"] == "trusted.net"

    b_form = BlockedSenderForm(
        data={"pattern": "junk@mail.com", "action": "discard", "description": ""}
    )
    assert b_form.is_valid()
    assert b_form.cleaned_data["action"] == "discard"

    invalid_form = TrustedSenderForm(data={"pattern": "   "})
    assert not invalid_form.is_valid()


def test_senders_panel_view(logged_in_client: Client):
    url = reverse("preferences:senders_panel")
    response: Any = logged_in_client.get(url + "?tab=trusted")
    assert response.status_code == 200
    assert b"Trusted Senders" in response.content

    response_blocked: Any = logged_in_client.get(url + "?tab=blocked")
    assert response_blocked.status_code == 200
    assert b"Blocked Senders" in response_blocked.content


def test_trusted_sender_add_and_delete_view(
    logged_in_client: Client,
    mail_account: MailAccount,
):
    add_url = reverse("preferences:trusted_sender_add")
    res_add: Any = logged_in_client.post(
        add_url,
        data={"pattern": "partner.com", "description": "Vendor"},
    )
    assert res_add.status_code == 200
    assert b"partner.com" in res_add.content
    assert is_sender_trusted(mail_account.account_key, "agent@partner.com")

    sender = cast(Any, TrustedSender).objects.get(
        account_key=mail_account.account_key,
        pattern="partner.com",
    )
    del_url = reverse("preferences:trusted_sender_delete", kwargs={"pk": sender.pk})
    res_del: Any = logged_in_client.post(del_url)
    assert res_del.status_code == 200
    assert not is_sender_trusted(mail_account.account_key, "agent@partner.com")


def test_blocked_sender_add_and_delete_view(
    logged_in_client: Client,
    mail_account: MailAccount,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "apps.preferences.views.save_blocked_senders_to_sieve",
        lambda req, acc: True,
    )
    add_url = reverse("preferences:blocked_sender_add")
    res_add: Any = logged_in_client.post(
        add_url,
        data={"pattern": "scam.org", "action": "trash", "description": "Phish"},
    )
    assert res_add.status_code == 200
    assert b"scam.org" in res_add.content
    assert is_sender_blocked(mail_account.account_key, "bot@scam.org") is not None

    blocked = cast(Any, BlockedSender).objects.get(
        account_key=mail_account.account_key,
        pattern="scam.org",
    )
    del_url = reverse("preferences:blocked_sender_delete", kwargs={"pk": blocked.pk})
    res_del: Any = logged_in_client.post(del_url)
    assert res_del.status_code == 200
    assert is_sender_blocked(mail_account.account_key, "bot@scam.org") is None
