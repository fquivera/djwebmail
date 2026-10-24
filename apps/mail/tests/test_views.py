"""Tests for the mail folder and message-list views."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.exceptions import ImapConnectionError
from apps.accounts.services.account import MailAccount
from apps.mail.services.mailbox import FolderNode, MessagePage, MessageSummary
from apps.mail.services.message import Attachment, MessageDetail


class FakeImapContext:
    """Context manager that stands in for a connected ImapService."""

    def __enter__(self) -> object:
        return object()

    def __exit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def mail_account() -> MailAccount:
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
        "apps.mail.views.get_mail_imap_service",
        lambda request: FakeImapContext(),
    )
    return client


@pytest.fixture
def mailbox_data(monkeypatch: pytest.MonkeyPatch) -> None:
    folders = (FolderNode(name="INBOX", label="INBOX", selectable=True),)
    page = MessagePage(
        folder="INBOX",
        page=1,
        page_size=50,
        total=1,
        page_count=1,
        messages=(
            MessageSummary(
                uid=7,
                subject="Hello from the test",
                sender="Alice <alice@example.com>",
                recipients="Bob <bob@example.com>",
                date=datetime(2026, 10, 22, 10, 0, tzinfo=UTC),
                flags=(),
                size=1024,
                is_seen=False,
                is_flagged=True,
            ),
        ),
        has_previous=False,
        has_next=False,
        previous_page=None,
        next_page=None,
    )
    monkeypatch.setattr("apps.mail.views.list_folders", lambda imap: folders)
    monkeypatch.setattr("apps.mail.views.list_messages", lambda imap, folder, **kwargs: page)


def test_mail_requires_login(client: Client) -> None:
    response: Any = client.get(reverse("mail:index"))

    assert response.status_code == 302
    assert response["Location"] == f"{reverse('accounts:login')}?next=%2Fmail%2F"


def test_mail_requires_login_for_htmx_uses_hx_redirect(client: Client) -> None:
    response: Any = client.get(reverse("mail:index"), HTTP_HX_REQUEST="true")

    assert response.status_code == 204
    assert response["HX-Redirect"] == f"{reverse('accounts:login')}?next=%2Fmail%2F"


def test_mail_renders_full_page(logged_in_client: Client, mailbox_data: None) -> None:
    response: Any = logged_in_client.get(reverse("mail:index"))

    assert response.status_code == 200
    template_names = [template.name for template in response.templates]
    assert "mail/index.html" in template_names
    assert b"Hello from the test" in response.content
    assert b"hx-get" in response.content
    assert b"/mail/message/INBOX/7/" in response.content
    assert b"hx-swap-oob" not in response.content


def test_mail_htmx_returns_fragment_and_refreshes_tree(
    logged_in_client: Client,
    mailbox_data: None,
) -> None:
    response: Any = logged_in_client.get(reverse("mail:index"), HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    template_names = [template.name for template in response.templates]
    assert "mail/_mailbox_response.html" in template_names
    assert "mail/index.html" not in template_names
    assert b"Hello from the test" in response.content
    assert b'hx-swap-oob="outerHTML"' in response.content
    assert "HX-Request" in response.headers["Vary"]


def test_mail_imap_error_renders_alert_for_full_page(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(imap: Any) -> None:
        raise ImapConnectionError("down")

    monkeypatch.setattr("apps.mail.views.list_folders", fail)

    response: Any = logged_in_client.get(reverse("mail:index"))

    assert response.status_code == 503
    assert b"Unable to load mail" in response.content


def test_mail_imap_error_stays_visible_after_htmx_swap(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(imap: Any) -> None:
        raise ImapConnectionError("down")

    monkeypatch.setattr("apps.mail.views.list_folders", fail)

    response: Any = logged_in_client.get(reverse("mail:index"), HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert b'role="alert"' in response.content
    assert b"Unable to load mail" in response.content


@pytest.fixture
def message_view_data(monkeypatch: pytest.MonkeyPatch) -> MessageDetail:
    detail = MessageDetail(
        uid=7,
        folder="INBOX",
        subject="Hello from the viewer",
        sender="Alice <alice@example.com>",
        recipients="Bob <bob@example.com>",
        cc="",
        date=datetime(2026, 10, 22, 10, 0, tzinfo=UTC),
        flags=(),
        is_seen=False,
        is_flagged=False,
        body_kind="html",
        body_html="<p>Sanitized body</p>",
        attachments=(),
        inline_cids={},
        remote_content_blocked=False,
    )
    monkeypatch.setattr("apps.mail.views.get_message", lambda imap, folder, uid: detail)
    return detail


def test_message_view_requires_login(client: Client) -> None:
    response: Any = client.get(reverse("mail:message", kwargs={"folder_name": "INBOX", "uid": 7}))

    assert response.status_code == 302
    assert response["Location"] == (
        f"{reverse('accounts:login')}?next=%2Fmail%2Fmessage%2FINBOX%2F7%2F"
    )


def test_message_view_renders_full_page(
    logged_in_client: Client,
    message_view_data: MessageDetail,
) -> None:
    response: Any = logged_in_client.get(
        reverse("mail:message", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 200
    template_names = [template.name for template in response.templates]
    assert "mail/message.html" in template_names
    assert b"Hello from the viewer" in response.content
    assert b"Sanitized body" in response.content


def test_message_view_returns_fragment_for_htmx(
    logged_in_client: Client,
    message_view_data: MessageDetail,
) -> None:
    response: Any = logged_in_client.get(
        reverse("mail:message", kwargs={"folder_name": "INBOX", "uid": 7}),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    template_names = [template.name for template in response.templates]
    assert "mail/_message_view.html" in template_names
    assert "mail/message.html" not in template_names
    assert b"Sanitized body" in response.content
    assert "HX-Request" in response.headers["Vary"]


def test_message_view_shows_remote_content_warning(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
    message_view_data: MessageDetail,
) -> None:
    blocked = MessageDetail(
        uid=7,
        folder="INBOX",
        subject="Images",
        sender="Alice <alice@example.com>",
        recipients="",
        cc="",
        date=None,
        flags=(),
        is_seen=False,
        is_flagged=False,
        body_kind="html",
        body_html="<p>Body</p>",
        attachments=(),
        inline_cids={},
        remote_content_blocked=True,
    )
    monkeypatch.setattr("apps.mail.views.get_message", lambda imap, folder, uid: blocked)

    response: Any = logged_in_client.get(
        reverse("mail:message", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 200
    assert b"Remote content was blocked" in response.content
    assert b"Load images" in response.content
    assert b'hx-post="/mail/message/INBOX/7/remote-images/"' in response.content


def test_message_remote_images_returns_proxied_body(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detail = MessageDetail(
        uid=7,
        folder="INBOX",
        subject="Images",
        sender="Alice <alice@example.com>",
        recipients="",
        cc="",
        date=None,
        flags=(),
        is_seen=False,
        is_flagged=False,
        body_kind="html",
        body_html='<img src="https://example.com/x.png">',
        attachments=(),
        inline_cids={},
        remote_content_blocked=True,
    )
    monkeypatch.setattr(
        "apps.mail.views.get_message",
        lambda imap, folder, uid, **kwargs: detail,
    )

    response: Any = logged_in_client.post(
        reverse("mail:message_remote_images", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 200
    template_names = [template.name for template in response.templates]
    assert "mail/_message_body.html" in template_names
    assert b"/mail/image-proxy/?u=https%3A%2F%2Fexample.com%2Fx.png" in response.content
    assert b"Remote content was blocked" not in response.content


def test_message_view_imap_error_renders_alert(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(imap: Any, folder: str, uid: int) -> None:
        raise ImapConnectionError("down")

    monkeypatch.setattr("apps.mail.views.get_message", fail)

    response: Any = logged_in_client.get(
        reverse("mail:message", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 503
    assert b"Unable to load mail" in response.content


def test_image_proxy_requires_login(client: Client) -> None:
    response: Any = client.get(reverse("mail:image_proxy"))

    assert response.status_code == 302
    assert response["Location"].startswith(reverse("accounts:login"))


def test_image_proxy_rejects_missing_url(logged_in_client: Client) -> None:
    response: Any = logged_in_client.get(reverse("mail:image_proxy"))

    assert response.status_code == 400


def test_image_proxy_rejects_private_url(logged_in_client: Client) -> None:
    response: Any = logged_in_client.get(
        reverse("mail:image_proxy"),
        {"u": "http://127.0.0.1/x.png"},
    )

    assert response.status_code == 404


def test_message_view_lists_attachments(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detail = MessageDetail(
        uid=7,
        folder="INBOX",
        subject="With attachment",
        sender="Alice <alice@example.com>",
        recipients="",
        cc="",
        date=None,
        flags=(),
        is_seen=False,
        is_flagged=False,
        body_kind="html",
        body_html="<p>Body</p>",
        attachments=(
            Attachment(
                part="2",
                filename="report.pdf",
                content_type="application/pdf",
                size=1024,
                disposition="attachment",
            ),
        ),
        inline_cids={},
        remote_content_blocked=False,
    )
    monkeypatch.setattr("apps.mail.views.get_message", lambda imap, folder, uid: detail)

    response: Any = logged_in_client.get(
        reverse("mail:message", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 200
    assert b"report.pdf" in response.content
    assert b"/mail/message/INBOX/7/attachment/2/" in response.content


def test_attachment_view_streams_part(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.mail.views.get_part",
        lambda imap, folder, uid, part: (
            b"%PDF-1.4",
            "application/pdf",
            "report.pdf",
            "attachment",
        ),
    )

    response: Any = logged_in_client.get(
        reverse("mail:attachment", kwargs={"folder_name": "INBOX", "uid": 7, "part": "2"})
    )

    assert response.status_code == 200
    assert response.content == b"%PDF-1.4"
    assert response["Content-Type"] == "application/pdf"
    assert 'attachment; filename="report.pdf"' in response["Content-Disposition"]


def test_attachment_view_requires_login(client: Client) -> None:
    response: Any = client.get(
        reverse("mail:attachment", kwargs={"folder_name": "INBOX", "uid": 7, "part": "2"})
    )

    assert response.status_code == 302


def test_inline_view_rejects_non_image(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.mail.views.get_part",
        lambda imap, folder, uid, part: (b"%PDF-1.4", "application/pdf", "report.pdf", "inline"),
    )

    response: Any = logged_in_client.get(
        reverse("mail:inline_image", kwargs={"folder_name": "INBOX", "uid": 7, "part": "2"})
    )

    assert response.status_code == 404


def test_inline_view_streams_image(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.mail.views.get_part",
        lambda imap, folder, uid, part: (b"\x89PNG", "image/png", "logo.png", "inline"),
    )

    response: Any = logged_in_client.get(
        reverse("mail:inline_image", kwargs={"folder_name": "INBOX", "uid": 7, "part": "2"})
    )

    assert response.status_code == 200
    assert response.content == b"\x89PNG"
    assert response["Content-Type"] == "image/png"
    assert "inline" in response["Content-Disposition"]
