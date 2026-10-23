"""Functional tests against a real IMAP/SMTP server.

They are skipped unless ``FUNCTIONAL_TESTS_ENABLED`` is true and the mail
endpoints are configured. The development Compose stack enables them; a plain
``uv run pytest`` on a workstation leaves them skipped.
"""

from __future__ import annotations

import smtplib
import time
from email.message import EmailMessage
from typing import Any, cast
from uuid import uuid4

import pytest
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse

from apps.accounts.services.account import MailAccount, resolve_mail_account
from apps.accounts.services.imap import ImapService
from apps.preferences.models import MailPreference

pytestmark = [pytest.mark.functional, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def require_functional_mail():
    """Skip instead of failing when the optional mail stack is absent."""
    if not settings.FUNCTIONAL_TESTS_ENABLED:
        pytest.skip("functional mail tests are disabled")
    if not settings.MAIL_IMAP_HOST or not settings.MAIL_SMTP_HOST:
        pytest.skip("functional mail endpoints are not configured")
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def account() -> MailAccount:
    return resolve_mail_account(settings.FUNCTIONAL_MAIL_USER)


@pytest.fixture
def password() -> str:
    return settings.FUNCTIONAL_MAIL_PASSWORD


def test_login_uses_real_imap_and_creates_server_side_session(client, account, password):
    response = client.post(
        reverse("accounts:login"),
        {"email": account.email, "password": password},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("mail:index")
    session = client.session
    assert session["mail_email"] == account.email
    assert session["mail_account_key"] == account.account_key
    assert "password" not in dict(session)
    assert cast(Any, MailPreference).objects.filter(account_key=account.account_key).exists()


def test_login_with_wrong_password_is_rejected_by_real_imap(client, account):
    response = client.post(
        reverse("accounts:login"),
        {"email": account.email, "password": f"wrong-{uuid4().hex}"},
    )

    assert response.status_code == 200
    assert b"Invalid email or password." in response.content
    assert client.session.get("mail_email") is None


def test_imap_service_lists_real_mailboxes(account, password):
    with ImapService(account, account.email, password) as imap:
        folder_names = {folder.name for folder in imap.list_folders()}

    assert "INBOX" in folder_names


def test_smtp_message_is_visible_over_imap(account, password):
    subject = f"djwebmail-functional-{uuid4().hex}"
    message = EmailMessage()
    message["From"] = account.email
    message["To"] = account.email
    message["Subject"] = subject
    message.set_content("Message delivered by the functional test suite.")

    with smtplib.SMTP(
        settings.MAIL_SMTP_HOST,
        settings.MAIL_SMTP_PORT,
        timeout=settings.MAIL_TIMEOUT_SECONDS,
    ) as smtp:
        smtp.send_message(message)

    deadline = time.monotonic() + settings.MAIL_TIMEOUT_SECONDS
    with ImapService(account, account.email, password) as imap:
        imap.select("INBOX", readonly=True)
        while True:
            uids = imap.search("ALL")
            for uid in reversed(uids):
                if subject.encode() in imap.fetch_message(uid).raw:
                    return
            if time.monotonic() >= deadline:
                pytest.fail("SMTP message did not become visible over IMAP")
            time.sleep(0.2)


def test_mail_view_lists_real_inbox_message(client, account, password):
    subject = f"djwebmail-mail-view-{uuid4().hex}"
    message = EmailMessage()
    message["From"] = account.email
    message["To"] = account.email
    message["Subject"] = subject
    message.set_content("Message rendered by the folder and message-list view.")

    with smtplib.SMTP(
        settings.MAIL_SMTP_HOST,
        settings.MAIL_SMTP_PORT,
        timeout=settings.MAIL_TIMEOUT_SECONDS,
    ) as smtp:
        smtp.send_message(message)

    deadline = time.monotonic() + settings.MAIL_TIMEOUT_SECONDS
    with ImapService(account, account.email, password) as imap:
        imap.select("INBOX", readonly=True)
        while True:
            if any(subject.encode() in imap.fetch_message(uid).raw for uid in imap.search("ALL")):
                break
            if time.monotonic() >= deadline:
                pytest.fail("SMTP message did not become visible over IMAP")
            time.sleep(0.2)

    login = client.post(
        reverse("accounts:login"),
        {"email": account.email, "password": password},
    )
    assert login.status_code == 302

    response = client.get(reverse("mail:index"))

    assert response.status_code == 200
    assert b"INBOX" in response.content
    assert subject.encode() in response.content
    assert b"hx-get" in response.content

    fragment = client.get(reverse("mail:index"), HTTP_HX_REQUEST="true")
    assert fragment.status_code == 200
    assert subject.encode() in fragment.content
    assert b"hx-swap-oob" in fragment.content


def test_message_viewer_sanitizes_html_and_blocks_remote_content(client, account, password):
    subject = f"djwebmail-viewer-{uuid4().hex}"
    message = EmailMessage()
    message["From"] = account.email
    message["To"] = account.email
    message["Subject"] = subject
    message.set_content("Plain fallback.")
    message.add_alternative(
        "<p>Hello <b>bold</b></p>"
        '<img src="https://example.com/tracked.png">'
        "<script>alert(1)</script>",
        subtype="html",
    )

    with smtplib.SMTP(
        settings.MAIL_SMTP_HOST,
        settings.MAIL_SMTP_PORT,
        timeout=settings.MAIL_TIMEOUT_SECONDS,
    ) as smtp:
        smtp.send_message(message)

    deadline = time.monotonic() + settings.MAIL_TIMEOUT_SECONDS
    uid: int | None = None
    with ImapService(account, account.email, password) as imap:
        imap.select("INBOX", readonly=True)
        while True:
            for candidate in reversed(imap.search("ALL")):
                if subject.encode() in imap.fetch_message(candidate).raw:
                    uid = candidate
                    break
            if uid is not None:
                break
            if time.monotonic() >= deadline:
                pytest.fail("SMTP message did not become visible over IMAP")
            time.sleep(0.2)

    login = client.post(
        reverse("accounts:login"),
        {"email": account.email, "password": password},
    )
    assert login.status_code == 302

    response = client.get(reverse("mail:message", kwargs={"folder_name": "INBOX", "uid": uid}))

    assert response.status_code == 200
    assert subject.encode() in response.content
    assert b"<b>bold</b>" in response.content
    assert b"<script" not in response.content
    assert b"<img" not in response.content
    assert b"Remote content was blocked" in response.content


def test_logout_clears_real_mail_session(client, account, password):
    login = client.post(
        reverse("accounts:login"),
        {"email": account.email, "password": password},
    )
    assert login.status_code == 302

    response = client.post(reverse("accounts:logout"))

    assert response.status_code == 302
    assert response["Location"] == reverse("accounts:login")
    assert client.session.get("mail_email") is None
