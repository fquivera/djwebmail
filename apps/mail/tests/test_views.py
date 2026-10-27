"""Tests for the mail folder and message-list views."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import translation

from apps.accounts.exceptions import ImapConnectionError
from apps.accounts.services.account import MailAccount
from apps.mail.services.mailbox import FolderNode, MessagePage, MessageSummary
from apps.mail.services.message import Attachment, MessageDetail
from apps.mail.services.search import SearchResult


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
def mailbox_data(monkeypatch: pytest.MonkeyPatch) -> MessagePage:
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
    return page


def test_mail_requires_login(client: Client) -> None:
    response: Any = client.get(reverse("mail:index"))

    assert response.status_code == 302
    assert response["Location"] == f"{reverse('accounts:login')}?next=%2Fmail%2F"


def test_mail_requires_login_for_htmx_uses_hx_redirect(client: Client) -> None:
    response: Any = client.get(reverse("mail:index"), HTTP_HX_REQUEST="true")

    assert response.status_code == 204
    assert response["HX-Redirect"] == f"{reverse('accounts:login')}?next=%2Fmail%2F"


def test_mail_renders_full_page(logged_in_client: Client, mailbox_data: MessagePage) -> None:
    response: Any = logged_in_client.get(reverse("mail:index"))

    assert response.status_code == 200
    template_names = [template.name for template in response.templates]
    assert "mail/index.html" in template_names
    assert b"Hello from the test" in response.content
    assert b"hx-get" in response.content
    assert b"/mail/message/INBOX/7/?view=message" in response.content
    assert b"hx-swap-oob" not in response.content
    assert b"data-mail-shell" in response.content
    assert b'data-view="list"' in response.content
    assert b'x-data="mailShell"' in response.content
    assert b"alpine-csp.min.js" in response.content
    assert b"js/app.js" in response.content
    assert b'hx-include="#current-folder"' in response.content


@pytest.mark.django_db
def test_mail_uses_page_size_from_session(
    logged_in_client: Client,
    mailbox_data: MessagePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def capture_page(imap: Any, folder: str, **kwargs: Any) -> MessagePage:
        captured.update(kwargs)
        return mailbox_data

    monkeypatch.setattr("apps.mail.views.list_messages", capture_page)
    session = logged_in_client.session
    session["mail_page_size"] = 25
    session.save()

    response: Any = logged_in_client.get(reverse("mail:index"))

    assert response.status_code == 200
    assert captured["page_size"] == 25


def test_mail_accepts_mobile_message_view(
    logged_in_client: Client,
    mailbox_data: MessagePage,
) -> None:
    response: Any = logged_in_client.get(reverse("mail:index"), {"view": "message"})

    assert response.status_code == 200
    assert b'data-view="message"' in response.content


def test_mail_rejects_unknown_mobile_view(
    logged_in_client: Client,
    mailbox_data: MessagePage,
) -> None:
    response: Any = logged_in_client.get(reverse("mail:index"), {"view": "bogus"})

    assert response.status_code == 200
    assert b'data-view="list"' in response.content


def test_mail_htmx_returns_fragment_and_refreshes_tree(
    logged_in_client: Client,
    mailbox_data: MessagePage,
) -> None:
    response: Any = logged_in_client.get(reverse("mail:index"), HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    template_names = [template.name for template in response.templates]
    assert "mail/_mailbox_response.html" in template_names
    assert "mail/index.html" not in template_names
    assert b"Hello from the test" in response.content
    assert b'id="folder-heading"' in response.content
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


def _search_page(*, total: int = 1, next_page: int | None = None) -> MessagePage:
    return MessagePage(
        folder="INBOX",
        page=1,
        page_size=50,
        total=total,
        page_count=2 if next_page else 1,
        messages=(
            MessageSummary(
                uid=7,
                subject="Hello from search",
                sender="Alice <alice@example.com>",
                recipients="Bob <bob@example.com>",
                date=datetime(2026, 10, 22, 10, 0, tzinfo=UTC),
                flags=(),
                size=1024,
                is_seen=False,
                is_flagged=False,
            ),
        )
        if total
        else (),
        has_previous=False,
        has_next=next_page is not None,
        previous_page=None,
        next_page=next_page,
        query_string="folder=INBOX&q=hello",
    )


def _global_search_page(*, next_page: int | None = None) -> MessagePage:
    return MessagePage(
        folder="INBOX",
        page=1,
        page_size=50,
        total=2,
        page_count=2 if next_page else 1,
        messages=(
            MessageSummary(
                uid=7,
                subject="Hello from global search",
                sender="Alice <alice@example.com>",
                recipients="Bob <bob@example.com>",
                date=datetime(2026, 10, 22, 10, 0, tzinfo=UTC),
                flags=(),
                size=1024,
                is_seen=False,
                is_flagged=False,
                folder="Sent",
            ),
        ),
        has_previous=False,
        has_next=next_page is not None,
        previous_page=None,
        next_page=next_page,
        query_string="folder=INBOX&scope=all&q=hello",
    )


@pytest.fixture
def search_data(monkeypatch: pytest.MonkeyPatch) -> MessagePage:
    page = _search_page()
    folders = (FolderNode(name="INBOX", label="INBOX", selectable=True),)
    monkeypatch.setattr("apps.mail.views.list_folders", lambda imap: folders)
    monkeypatch.setattr(
        "apps.mail.views.search_messages",
        lambda imap, filters, **kwargs: SearchResult(page=page),
    )
    return page


def test_search_requires_login(client: Client) -> None:
    response: Any = client.get(reverse("mail:search"))

    assert response.status_code == 302
    assert response["Location"] == f"{reverse('accounts:login')}?next=%2Fmail%2Fsearch%2F"


def test_search_renders_full_page_with_bound_form(
    logged_in_client: Client,
    search_data: MessagePage,
) -> None:
    response: Any = logged_in_client.get(
        reverse("mail:search"),
        {
            "folder": "INBOX",
            "q": "hello",
            "from": "alice@example.com",
            "unread": "on",
        },
    )

    assert response.status_code == 200
    template_names = [template.name for template in response.templates]
    assert "mail/index.html" in template_names
    assert b"Hello from search" in response.content
    assert b'name="q" value="hello"' in response.content
    assert b'name="from" value="alice@example.com"' in response.content
    assert b'name="folder" value="INBOX"' in response.content
    assert b"checked" in response.content


def test_search_htmx_returns_list_fragment(
    logged_in_client: Client,
    search_data: MessagePage,
) -> None:
    response: Any = logged_in_client.get(
        reverse("mail:search"),
        {"folder": "INBOX", "q": "hello"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    template_names = [template.name for template in response.templates]
    assert "mail/_message_list.html" in template_names
    assert "mail/index.html" not in template_names
    assert b"Hello from search" in response.content
    assert b"<html" not in response.content
    assert "HX-Request" in response.headers["Vary"]


def test_search_pagination_preserves_filters(
    logged_in_client: Client,
    search_data: MessagePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _search_page(total=3, next_page=2)
    monkeypatch.setattr(
        "apps.mail.views.search_messages",
        lambda imap, filters, **kwargs: SearchResult(page=page),
    )

    response: Any = logged_in_client.get(
        reverse("mail:search"),
        {"folder": "INBOX", "q": "hello"},
    )

    assert b'href="/mail/search/?folder=INBOX&amp;q=hello&amp;page=2"' in response.content
    assert b'hx-get="/mail/search/?folder=INBOX&amp;q=hello&amp;page=2"' in response.content
    assert b'hx-target="#message-list-results"' in response.content


def test_search_without_results_shows_search_empty_state(
    logged_in_client: Client,
    search_data: MessagePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.mail.views.search_messages",
        lambda imap, filters, **kwargs: SearchResult(page=_search_page(total=0)),
    )

    response: Any = logged_in_client.get(
        reverse("mail:search"),
        {"folder": "INBOX", "q": "nothing"},
    )

    assert response.status_code == 200
    assert b"No messages match your search." in response.content


def test_search_shows_ascii_fallback_notice(
    logged_in_client: Client,
    search_data: MessagePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.mail.views.search_messages",
        lambda imap, filters, **kwargs: SearchResult(
            page=_search_page(),
            used_ascii_fallback=True,
        ),
    )

    response: Any = logged_in_client.get(
        reverse("mail:search"),
        {"folder": "INBOX", "q": "búsqueda"},
    )

    assert response.status_code == 200
    assert b"The server does not support UTF-8 search" in response.content


def test_search_rejects_reversed_dates(
    logged_in_client: Client,
    search_data: MessagePage,
) -> None:
    response: Any = logged_in_client.get(
        reverse("mail:search"),
        {
            "folder": "INBOX",
            "date_from": "2026-10-31",
            "date_to": "2026-10-01",
        },
    )

    assert response.status_code == 200
    assert b"End date must be on or after start date." in response.content
    assert b"Check the search filters." in response.content


def test_search_rejects_reversed_dates_for_htmx(
    logged_in_client: Client,
    search_data: MessagePage,
) -> None:
    response: Any = logged_in_client.get(
        reverse("mail:search"),
        {
            "folder": "INBOX",
            "date_from": "2026-10-31",
            "date_to": "2026-10-01",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    template_names = [template.name for template in response.templates]
    assert "mail/_message_list.html" in template_names
    assert b'role="alert"' in response.content
    assert b"Check the search filters." in response.content


def test_search_global_scope_passes_global_filters(
    logged_in_client: Client,
    search_data: MessagePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def capture_search(imap: Any, filters: Any, **kwargs: Any) -> SearchResult:
        captured["filters"] = filters
        return SearchResult(page=_global_search_page())

    monkeypatch.setattr("apps.mail.views.search_messages", capture_search)

    response: Any = logged_in_client.get(
        reverse("mail:search"),
        {"folder": "INBOX", "scope": "all", "q": "hello"},
    )

    assert response.status_code == 200
    filters = captured["filters"]
    assert filters.is_global is True
    assert filters.scope == "all"


def test_search_global_scope_shows_folder_and_global_pagination(
    logged_in_client: Client,
    search_data: MessagePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.mail.views.search_messages",
        lambda imap, filters, **kwargs: SearchResult(page=_global_search_page(next_page=2)),
    )

    response: Any = logged_in_client.get(
        reverse("mail:search"),
        {"folder": "INBOX", "scope": "all", "q": "hello"},
    )

    assert response.status_code == 200
    assert b"Hello from global search" in response.content
    assert b"Sent</span>" in response.content
    assert b"folder=INBOX&amp;scope=all&amp;q=hello&amp;page=2" in response.content
    assert b"All folders" in response.content


def test_search_global_scope_htmx_updates_heading(
    logged_in_client: Client,
    search_data: MessagePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.mail.views.search_messages",
        lambda imap, filters, **kwargs: SearchResult(page=_global_search_page()),
    )

    response: Any = logged_in_client.get(
        reverse("mail:search"),
        {"folder": "INBOX", "scope": "all", "q": "hello"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert "mail/_search_response.html" in [item.name for item in response.templates]
    assert b'hx-swap-oob="outerHTML"' in response.content
    assert b"All folders" in response.content
    assert b"<html" not in response.content


def test_search_global_scope_shows_truncation_notice(
    logged_in_client: Client,
    search_data: MessagePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.mail.views.search_messages",
        lambda imap, filters, **kwargs: SearchResult(
            page=_global_search_page(),
            truncated=True,
        ),
    )

    response: Any = logged_in_client.get(
        reverse("mail:search"),
        {"folder": "INBOX", "scope": "all", "q": "hello"},
    )

    assert response.status_code == 200
    assert b"Results are limited to the newest" in response.content


def test_search_form_exposes_scope_selector(
    logged_in_client: Client,
    search_data: MessagePage,
) -> None:
    response: Any = logged_in_client.get(reverse("mail:search"), {"folder": "INBOX"})

    assert response.status_code == 200
    assert b'name="scope"' in response.content
    assert b"All folders" in response.content


def test_palette_requires_login(client: Client) -> None:
    response: Any = client.get(reverse("mail:palette"))

    assert response.status_code == 302
    assert response["Location"] == f"{reverse('accounts:login')}?next=%2Fmail%2Fpalette%2F"


def test_palette_empty_query_does_not_search(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_search(*args: object, **kwargs: object) -> None:
        raise AssertionError("empty palette query must not reach IMAP search")

    monkeypatch.setattr("apps.mail.views.search_messages", fail_search)

    response: Any = logged_in_client.get(reverse("mail:palette"), {"folder": "INBOX"})

    assert response.status_code == 200
    template_names = [template.name for template in response.templates]
    assert "mail/_palette_results.html" in template_names
    assert b"Type to search all folders." in response.content


def test_palette_rejects_long_query(logged_in_client: Client) -> None:
    response: Any = logged_in_client.get(
        reverse("mail:palette"),
        {"folder": "INBOX", "q": "x" * 201},
    )

    assert response.status_code == 200
    assert b"Check the search filters." in response.content


def test_palette_uses_global_search(
    logged_in_client: Client,
    search_data: MessagePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def capture_search(imap: Any, filters: Any, **kwargs: Any) -> SearchResult:
        captured["filters"] = filters
        return SearchResult(page=_global_search_page())

    monkeypatch.setattr("apps.mail.views.search_messages", capture_search)

    response: Any = logged_in_client.get(
        reverse("mail:palette"),
        {"folder": "INBOX", "q": "hello"},
    )

    assert response.status_code == 200
    assert captured["filters"].is_global is True
    assert b"Hello from global search" in response.content
    assert b"Sent" in response.content
    assert b"scope=all" in response.content


def test_palette_renders_current_folder_results(
    logged_in_client: Client,
    search_data: MessagePage,
) -> None:
    response: Any = logged_in_client.get(
        reverse("mail:palette"),
        {"folder": "INBOX", "q": "hello"},
    )

    assert response.status_code == 200
    template_names = [template.name for template in response.templates]
    assert "mail/_palette_results.html" in template_names
    assert b"Hello from search" in response.content
    assert b"/mail/message/INBOX/7/?view=message" in response.content
    assert b'hx-target="#message-viewer"' in response.content
    assert b"data-palette-close" in response.content


def test_palette_matches_folder_names(
    logged_in_client: Client,
    search_data: MessagePage,
) -> None:
    response: Any = logged_in_client.get(
        reverse("mail:palette"),
        {"folder": "INBOX", "q": "inb"},
    )

    assert response.status_code == 200
    assert b"Folders" in response.content
    assert b"/mail/folder/INBOX/?view=list" in response.content


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
    monkeypatch.setattr("apps.mail.views.list_folders", lambda imap: ())
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
    assert b'x-data="messageActions"' in response.content
    assert b'data-shortcut="toggle-read"' in response.content
    assert b'data-shortcut="reply"' in response.content
    assert b"alpine-csp.min.js" in response.content
    assert b'name="standalone" value="1"' in response.content
    # The alert wrapper owns visibility so daisyUI's .alert display rule cannot
    # keep a successful auto-read request showing the error.
    assert b'<div class="when-flag-error">' in response.content
    assert b'class="alert alert-error text-sm"' in response.content
    assert b"alert alert-error when-flag-error" not in response.content


def test_message_view_keeps_global_scope_for_flags(
    logged_in_client: Client,
    message_view_data: MessageDetail,
) -> None:
    response: Any = logged_in_client.get(
        reverse("mail:message", kwargs={"folder_name": "INBOX", "uid": 7}),
        {"scope": "all", "view": "message"},
    )

    assert response.status_code == 200
    assert b'name="scope" value="all"' in response.content


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
    assert b'name="standalone" value="1"' not in response.content
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
    monkeypatch.setattr("apps.mail.views.list_folders", lambda imap: ())

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


def _flags_double(
    monkeypatch: pytest.MonkeyPatch,
    *,
    flags: tuple[str, ...],
) -> None:
    summary = MessageSummary(
        uid=7,
        subject="Hello",
        sender="Alice <alice@example.com>",
        recipients="",
        date=None,
        flags=flags,
        size=1,
        is_seen="\\Seen" in flags,
        is_flagged="\\Flagged" in flags,
        folder="INBOX",
    )
    detail = MessageDetail(
        uid=7,
        folder="INBOX",
        subject="Hello",
        sender="Alice <alice@example.com>",
        recipients="",
        cc="",
        date=None,
        flags=flags,
        is_seen="\\Seen" in flags,
        is_flagged="\\Flagged" in flags,
        body_kind="html",
        body_html="<p>Body</p>",
        attachments=(),
        inline_cids={},
        remote_content_blocked=False,
    )
    monkeypatch.setattr(
        "apps.mail.views.set_message_flags",
        lambda imap, folder, uid, **kwargs: summary,
    )
    monkeypatch.setattr("apps.mail.views.get_message", lambda imap, folder, uid: detail)
    monkeypatch.setattr("apps.mail.views.list_folders", lambda imap: ())


def test_message_flags_requires_login(client: Client) -> None:
    response: Any = client.post(
        reverse("mail:message_flags", kwargs={"folder_name": "INBOX", "uid": 7}),
        {"action": "read"},
    )

    assert response.status_code == 302


def test_message_flags_rejects_invalid_action(logged_in_client: Client) -> None:
    response: Any = logged_in_client.post(
        reverse("mail:message_flags", kwargs={"folder_name": "INBOX", "uid": 7}),
        {"action": "bogus"},
    )

    assert response.status_code == 400


def test_message_flags_marks_read_returns_oob_row(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _flags_double(monkeypatch, flags=("\\Seen",))

    response: Any = logged_in_client.post(
        reverse("mail:message_flags", kwargs={"folder_name": "INBOX", "uid": 7}),
        {"action": "read"},
    )

    assert response.status_code == 200
    assert b'hx-swap-oob="outerHTML"' in response.content
    assert b'id="msg-7"' in response.content
    assert b"<article" not in response.content


def test_message_flags_star_returns_only_oob_row(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _flags_double(monkeypatch, flags=("\\Flagged",))

    response: Any = logged_in_client.post(
        reverse("mail:message_flags", kwargs={"folder_name": "INBOX", "uid": 7}),
        {"action": "star"},
    )

    assert response.status_code == 200
    assert b'hx-swap-oob="outerHTML"' in response.content
    assert b'id="msg-7"' in response.content
    assert b"<article" not in response.content


def test_message_flags_global_scope_keeps_folder_badge(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _flags_double(monkeypatch, flags=("\\Seen",))

    response: Any = logged_in_client.post(
        reverse("mail:message_flags", kwargs={"folder_name": "INBOX", "uid": 7}),
        {"action": "read", "scope": "all"},
    )

    assert response.status_code == 200
    assert b"INBOX</span>" in response.content
    assert b"scope=all" in response.content


def test_message_flags_standalone_page_returns_no_content(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _flags_double(monkeypatch, flags=("\\Seen",))

    response: Any = logged_in_client.post(
        reverse("mail:message_flags", kwargs={"folder_name": "INBOX", "uid": 7}),
        {"action": "read", "standalone": "1"},
    )

    assert response.status_code == 204
    assert response.content == b""


def test_message_flags_returns_failure_for_optimistic_revert(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise ImapConnectionError("down")

    monkeypatch.setattr("apps.mail.views.set_message_flags", fail)

    response: Any = logged_in_client.post(
        reverse("mail:message_flags", kwargs={"folder_name": "INBOX", "uid": 7}),
        {"action": "star"},
    )

    assert response.status_code == 503
    assert b"<article" not in response.content


def test_message_move_requires_login(client: Client) -> None:
    response: Any = client.post(
        reverse("mail:message_move", kwargs={"folder_name": "INBOX", "uid": 7}),
        {"dest": "Archive"},
    )

    assert response.status_code == 302


def test_message_move_rejects_missing_dest(logged_in_client: Client) -> None:
    response: Any = logged_in_client.post(
        reverse("mail:message_move", kwargs={"folder_name": "INBOX", "uid": 7}),
    )

    assert response.status_code == 400


def test_message_move_redirects_to_destination(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("apps.mail.views.move_message", lambda imap, folder, uid, dest: None)

    response: Any = logged_in_client.post(
        reverse("mail:message_move", kwargs={"folder_name": "INBOX", "uid": 7}),
        {"dest": "Archive"},
    )

    assert response.status_code == 302
    assert response["Location"] == "/mail/folder/Archive/"


def test_message_move_htmx_uses_hx_redirect(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("apps.mail.views.move_message", lambda imap, folder, uid, dest: None)

    response: Any = logged_in_client.post(
        reverse("mail:message_move", kwargs={"folder_name": "INBOX", "uid": 7}),
        {"dest": "Archive"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 204
    assert response["HX-Redirect"] == "/mail/folder/Archive/"


def test_message_delete_requires_login(client: Client) -> None:
    response: Any = client.post(
        reverse("mail:message_delete", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 302


def test_message_delete_redirects_to_folder(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("apps.mail.views.delete_message", lambda imap, folder, uid: None)

    response: Any = logged_in_client.post(
        reverse("mail:message_delete", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 302
    assert response["Location"] == "/mail/folder/INBOX/"


def test_message_delete_htmx_uses_hx_redirect(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("apps.mail.views.delete_message", lambda imap, folder, uid: None)

    response: Any = logged_in_client.post(
        reverse("mail:message_delete", kwargs={"folder_name": "INBOX", "uid": 7}),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 204
    assert response["HX-Redirect"] == "/mail/folder/INBOX/"


def test_message_view_renders_delete_confirmation(
    logged_in_client: Client,
    message_view_data: MessageDetail,
) -> None:
    response: Any = logged_in_client.get(
        reverse("mail:message", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 200
    assert b'data-confirm-open="delete-dialog-7"' in response.content
    assert b'id="delete-dialog-7"' in response.content
    assert b"/mail/message/INBOX/7/delete/" in response.content


def test_mail_row_renders_hover_quick_actions(
    logged_in_client: Client,
    mailbox_data: MessagePage,
) -> None:
    response: Any = logged_in_client.get(reverse("mail:index"))

    assert response.status_code == 200
    assert reverse("compose:reply", kwargs={"folder_name": "INBOX", "uid": 7}).encode() in (
        response.content
    )
    assert reverse("compose:reply_all", kwargs={"folder_name": "INBOX", "uid": 7}).encode() in (
        response.content
    )
    assert reverse("compose:forward", kwargs={"folder_name": "INBOX", "uid": 7}).encode() in (
        response.content
    )
    assert reverse("mail:message_delete", kwargs={"folder_name": "INBOX", "uid": 7}).encode() in (
        response.content
    )
    assert reverse("mail:message_flags", kwargs={"folder_name": "INBOX", "uid": 7}).encode() in (
        response.content
    )


def test_message_view_renders_reply_all_and_details(
    logged_in_client: Client,
    message_view_data: MessageDetail,
) -> None:
    response: Any = logged_in_client.get(
        reverse("mail:message", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 200
    assert reverse("compose:reply_all", kwargs={"folder_name": "INBOX", "uid": 7}).encode() in (
        response.content
    )
    assert b"Show details" in response.content


@pytest.mark.django_db
def test_message_view_auto_loads_remote_images_when_preference_is_always(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detail = MessageDetail(
        uid=7,
        folder="INBOX",
        subject="Auto remote images",
        sender="Alice <alice@example.com>",
        recipients="Bob <bob@example.com>",
        cc="",
        date=None,
        flags=(),
        is_seen=True,
        is_flagged=False,
        body_kind="html",
        body_html='<img src="https://example.com/banner.png">',
        attachments=(),
        inline_cids={},
        remote_content_blocked=True,
    )
    monkeypatch.setattr("apps.mail.views.get_message", lambda imap, folder, uid: detail)
    monkeypatch.setattr("apps.mail.views.list_folders", lambda imap: ())
    session = logged_in_client.session
    session["mail_remote_images"] = "always"
    session.save()

    response: Any = logged_in_client.get(
        reverse("mail:message", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 200
    assert b"/mail/image-proxy/?u=https%3A%2F%2Fexample.com%2Fbanner.png" in response.content
    assert b"Remote content was blocked" not in response.content


def test_messages_batch_marks_selected_messages_read(
    logged_in_client: Client,
    mailbox_data: MessagePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def capture_batch_flags(imap: Any, folder: str, uids: Any, **kwargs: Any) -> None:
        captured["folder"] = folder
        captured["uids"] = uids
        captured["kwargs"] = kwargs

    monkeypatch.setattr("apps.mail.views.batch_set_flags", capture_batch_flags)

    response: Any = logged_in_client.post(
        reverse("mail:messages_batch", kwargs={"folder_name": "INBOX"}),
        {"uids": ["7", "8"], "action": "read"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert captured["folder"] == "INBOX"
    assert captured["uids"] == (7, 8)
    assert captured["kwargs"] == {"add": ("\\Seen",), "remove": ()}
    assert b'id="message-list-items"' in response.content


def test_messages_batch_deletes_selected_messages(
    logged_in_client: Client,
    mailbox_data: MessagePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted: dict[str, Any] = {}

    def capture_batch_delete(imap: Any, folder: str, uids: Any) -> None:
        deleted["folder"] = folder
        deleted["uids"] = uids

    monkeypatch.setattr("apps.mail.views.batch_delete_messages", capture_batch_delete)

    response: Any = logged_in_client.post(
        reverse("mail:messages_batch", kwargs={"folder_name": "INBOX"}),
        {"uids": "7,9", "action": "delete"},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("mail:folder", kwargs={"folder_name": "INBOX"})
    assert deleted == {"folder": "INBOX", "uids": (7, 9)}


def test_messages_batch_rejects_empty_selection(logged_in_client: Client) -> None:
    response: Any = logged_in_client.post(
        reverse("mail:messages_batch", kwargs={"folder_name": "INBOX"}),
        {"action": "read"},
    )

    assert response.status_code == 400


def test_mailbox_renders_spanish_folder_labels(
    logged_in_client: Client,
    mailbox_data: MessagePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with translation.override("es"):
        folders = (
            FolderNode(name="INBOX", label="Bandeja de entrada", selectable=True),
            FolderNode(name="Sent", label="Enviados", selectable=True),
        )
        monkeypatch.setattr("apps.mail.views.list_folders", lambda imap: folders)
        response: Any = logged_in_client.get(reverse("mail:index"))

    assert response.status_code == 200
    assert b"Bandeja de entrada" in response.content
    assert b"Enviados" in response.content


def test_folder_create_creates_folder_and_redirects_htmx(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_create(imap: Any, name: str, *, parent: str = "") -> str:
        captured["name"] = name
        captured["parent"] = parent
        return f"{parent}/{name}" if parent else name

    monkeypatch.setattr("apps.mail.views.create_user_folder", fake_create)

    response: Any = logged_in_client.post(
        reverse("mail:folder_create"),
        {"name": "Facturas", "parent": "INBOX"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 204
    assert captured == {"name": "Facturas", "parent": "INBOX"}
    assert response["HX-Redirect"] == "/mail/folder/INBOX/Facturas/?view=list"


def test_folder_create_rejects_invalid_name(logged_in_client: Client) -> None:
    response: Any = logged_in_client.post(
        reverse("mail:folder_create"),
        {"name": "bad/name"},
    )

    assert response.status_code == 400


def test_message_archive_moves_to_archive_and_redirects_to_folder(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archived: dict[str, Any] = {}

    def fake_archive(imap: Any, folder: str, uid: int) -> str:
        archived["folder"] = folder
        archived["uid"] = uid
        return "Archive"

    monkeypatch.setattr("apps.mail.views.archive_message", fake_archive)

    response: Any = logged_in_client.post(
        reverse("mail:message_archive", kwargs={"folder_name": "INBOX", "uid": 7}),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 204
    assert response["HX-Redirect"] == reverse("mail:folder", kwargs={"folder_name": "INBOX"})
    assert archived == {"folder": "INBOX", "uid": 7}


def test_messages_batch_archive_moves_selected_uids(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archived: dict[str, Any] = {}

    def fake_batch_archive(imap: Any, folder: str, uids: tuple[int, ...]) -> str:
        archived["folder"] = folder
        archived["uids"] = uids
        return "Archive"

    monkeypatch.setattr("apps.mail.views.batch_archive_messages", fake_batch_archive)

    response: Any = logged_in_client.post(
        reverse("mail:messages_batch", kwargs={"folder_name": "INBOX"}),
        {"uids": "7,9", "action": "archive"},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("mail:folder", kwargs={"folder_name": "INBOX"})
    assert archived == {"folder": "INBOX", "uids": (7, 9)}


def test_attachment_preview_renders_modal_fragment_for_pdf_and_text(
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
        reverse(
            "mail:attachment_preview",
            kwargs={"folder_name": "INBOX", "uid": 7, "part": "2"},
        )
    )

    assert response.status_code == 200
    assert b"report.pdf" in response.content
    assert b"<iframe" in response.content
    assert b"/mail/message/INBOX/7/attachment/2/inline/" in response.content
    assert b"data-dialog-close" in response.content

    monkeypatch.setattr(
        "apps.mail.views.get_part",
        lambda imap, folder, uid, part: (
            b"Line 1\nLine 2 <script>alert(1)</script>",
            "text/plain",
            "notes.txt",
            "attachment",
        ),
    )

    text_response: Any = logged_in_client.get(
        reverse(
            "mail:attachment_preview",
            kwargs={"folder_name": "INBOX", "uid": 7, "part": "3"},
        )
    )

    assert text_response.status_code == 200
    assert b"<pre" in text_response.content
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in text_response.content


def test_attachment_inline_allows_safe_preview_types_and_rejects_unsafe(
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
        reverse(
            "mail:attachment_inline",
            kwargs={"folder_name": "INBOX", "uid": 7, "part": "2"},
        )
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"] == 'inline; filename="report.pdf"'
    assert response["X-Frame-Options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in response["Content-Security-Policy"]

    monkeypatch.setattr(
        "apps.mail.views.get_part",
        lambda imap, folder, uid, part: (
            b"<svg><script>alert(1)</script></svg>",
            "image/svg+xml",
            "bad.svg",
            "attachment",
        ),
    )

    unsafe_response: Any = logged_in_client.get(
        reverse(
            "mail:attachment_inline",
            kwargs={"folder_name": "INBOX", "uid": 7, "part": "3"},
        )
    )

    assert unsafe_response.status_code == 404
