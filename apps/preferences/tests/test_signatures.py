"""Unit tests for AccountSignature model, services, and views."""

from __future__ import annotations

from typing import Any, cast

import pytest
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.accounts.constants import SESSION_SIGNATURE_KEY
from apps.accounts.services.account import MailAccount
from apps.preferences.models import AccountSignature, MailPreference
from apps.preferences.services import (
    get_account_signatures,
    get_active_signatures,
    get_default_signature,
    sanitize_signature_html,
    sync_default_signature_to_session,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def mail_account() -> MailAccount:
    return MailAccount(
        email="signatureuser@example.com",
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


def test_sanitize_signature_html_strips_xss():
    dirty = (
        '<p style="color: blue;">Hello</p><script>alert(1)</script><img src="x" onerror="evil()">'
    )
    clean = sanitize_signature_html(dirty)
    assert "<script>" not in clean
    assert "onerror" not in clean
    assert '<p style="color: blue;">Hello</p>' in clean


def test_account_signature_default_unicity(mail_account: MailAccount):
    sig1 = cast(Any, AccountSignature).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
        name="Signature 1",
        content_html="<b>One</b>",
        is_default=True,
    )
    assert sig1.is_default is True

    sig2 = cast(Any, AccountSignature).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
        name="Signature 2",
        content_html="<b>Two</b>",
        is_default=True,
    )
    sig1.refresh_from_db()
    assert sig2.is_default is True
    assert sig1.is_default is False
    assert " (default)" in str(sig2)


def test_get_account_signatures_migrates_legacy_preference(mail_account: MailAccount):
    # No signatures exist initially
    signatures = get_account_signatures(
        mail_account.account_key,
        email=mail_account.email,
        seed_from_pref="<p>Legacy signature</p>",
    )
    assert len(signatures) == 1
    assert signatures[0].name == "Firma predeterminada" or "Default" in signatures[0].name
    assert "Legacy signature" in signatures[0].content_html
    assert signatures[0].is_default is True
    assert signatures[0].is_active is True


def test_get_active_and_default_signatures(mail_account: MailAccount):
    cast(Any, AccountSignature).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
        name="Work",
        content_html="Work signature",
        is_default=True,
        is_active=True,
    )
    cast(Any, AccountSignature).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
        name="Inactive",
        content_html="Draft",
        is_default=False,
        is_active=False,
    )

    active = get_active_signatures(mail_account.account_key)
    assert len(active) == 1
    assert active[0].name == "Work"

    default = get_default_signature(mail_account.account_key)
    assert default is not None
    assert default.name == "Work"


def test_sync_default_signature_to_session(mail_account: MailAccount):
    rf = RequestFactory()
    request = rf.get("/")
    request.mail_account = mail_account  # type: ignore[attr-defined]
    request.session = {}  # type: ignore[attr-defined]

    cast(Any, MailPreference).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
    )
    cast(Any, AccountSignature).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
        name="Work",
        content_html="Work signature",
        is_default=True,
        is_active=True,
    )

    sync_default_signature_to_session(request)
    session = getattr(request, "session", {})
    assert session[SESSION_SIGNATURE_KEY] == "Work signature"

    pref = cast(Any, MailPreference).objects.get(account_key=mail_account.account_key)
    assert pref.signature_html == "Work signature"


def test_signatures_panel_view_get(logged_in_client: Client):
    url = reverse("preferences:signatures_panel")
    response: Any = logged_in_client.get(url)
    assert response.status_code == 200
    assert "signatures-panel" in response.content.decode()


def test_signature_modal_view_create_and_edit(
    logged_in_client: Client,
    mail_account: MailAccount,
):
    modal_url = reverse("preferences:signature_modal")
    # 1. Create modal
    resp: Any = logged_in_client.get(modal_url)
    assert resp.status_code == 200
    assert "signature-modal" in resp.content.decode()

    # 2. Edit modal
    sig = cast(Any, AccountSignature).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
        name="Personal",
        content_html="<i>Cheers</i>",
    )
    resp_edit: Any = logged_in_client.get(f"{modal_url}?sig_id={sig.id}")
    assert resp_edit.status_code == 200
    assert "Personal" in resp_edit.content.decode()


def test_signature_save_view_post_new_and_update(
    logged_in_client: Client,
    mail_account: MailAccount,
):
    save_url = reverse("preferences:signature_save")
    payload = {
        "name": "Mobile",
        "content_html": "<div>Sent from mobile</div>",
        "is_active": "on",
    }
    response: Any = logged_in_client.post(save_url, payload)
    assert response.status_code == 200
    assert "Mobile" in response.content.decode()

    sig = cast(Any, AccountSignature).objects.get(name="Mobile")
    # First signature created is automatically set to default
    assert sig.is_default is True
    assert sig.is_active is True

    # Update signature
    update_payload = {
        "sig_id": str(sig.id),
        "name": "Mobile Updated",
        "content_html": "<div>Sent from my phone</div>",
        "is_active": "on",
        "is_default": "on",
    }
    response2: Any = logged_in_client.post(save_url, update_payload)
    assert response2.status_code == 200
    assert "Mobile Updated" in response2.content.decode()


def test_signature_set_default_view(
    logged_in_client: Client,
    mail_account: MailAccount,
):
    sig1 = cast(Any, AccountSignature).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
        name="Sig 1",
        is_default=True,
    )
    sig2 = cast(Any, AccountSignature).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
        name="Sig 2",
        is_default=False,
    )

    url = reverse("preferences:signature_set_default", kwargs={"sig_id": sig2.id})
    response: Any = logged_in_client.post(url)
    assert response.status_code == 200

    sig1.refresh_from_db()
    sig2.refresh_from_db()
    assert sig2.is_default is True
    assert sig1.is_default is False


def test_signature_toggle_active_and_delete(
    logged_in_client: Client,
    mail_account: MailAccount,
):
    sig = cast(Any, AccountSignature).objects.create(
        account_key=mail_account.account_key,
        email=mail_account.email,
        name="To Toggle",
        is_default=True,
        is_active=True,
    )

    toggle_url = reverse("preferences:signature_toggle_active", kwargs={"sig_id": sig.id})
    logged_in_client.post(toggle_url)
    sig.refresh_from_db()
    assert sig.is_active is False
    assert sig.is_default is False

    delete_url = reverse("preferences:signature_delete", kwargs={"sig_id": sig.id})
    logged_in_client.post(delete_url)
    assert not cast(Any, AccountSignature).objects.filter(pk=sig.id).exists()
