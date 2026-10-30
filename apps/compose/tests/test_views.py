"""Tests for the compose, reply, forward, and send views."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.accounts.exceptions import ImapConnectionError, SmtpAuthError
from apps.accounts.services.account import MailAccount
from apps.compose.attachments import list_attachments
from apps.compose.drafts import save_draft
from apps.mail.services.message import MessageDetail

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_compose_cache():
    cache.clear()
    yield
    cache.clear()


def session_key(client: Client) -> str:
    key = client.session.session_key
    if key is None:
        client.get(reverse("compose:new"))
        key = client.session.session_key
    assert key
    return key


def upload_attachment(
    client: Client,
    *,
    name: str = "report.txt",
    content: bytes = b"hello",
    content_type: str = "text/plain",
) -> Any:
    return client.post(
        reverse("compose:attachments"),
        {"attachments": SimpleUploadedFile(name, content, content_type=content_type)},
    )


class FakeImapContext:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, *exc: object) -> None:
        return None


class FakeSmtp:
    def __init__(self) -> None:
        self.sent: tuple[str, list[str], bytes] | None = None

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def send(self, sender: str, recipients: list[str], raw: bytes) -> None:
        self.sent = (sender, list(recipients), raw)


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
    return client


@pytest.fixture
def detail() -> MessageDetail:
    return MessageDetail(
        uid=7,
        folder="INBOX",
        subject="Original subject",
        sender="Alice <alice@example.com>",
        recipients="Bob <bob@example.com>",
        cc="",
        date=datetime(2026, 10, 22, 10, 0, tzinfo=UTC),
        flags=(),
        is_seen=False,
        is_flagged=False,
        body_kind="plain",
        body_html="<p>Original body</p>",
        attachments=(),
        inline_cids={},
        remote_content_blocked=False,
    )


def test_compose_requires_login(client: Client) -> None:
    response: Any = client.get(reverse("compose:new"))

    assert response.status_code == 302
    assert response["Location"] == f"{reverse('accounts:login')}?next=%2Fcompose%2F"


def test_compose_renders_empty_form(logged_in_client: Client) -> None:
    response: Any = logged_in_client.get(reverse("compose:new"))

    assert response.status_code == 200
    assert b'name="to"' in response.content
    assert b'name="body"' in response.content
    assert b"Send" in response.content
    assert b'id="insert-image-modal"' in response.content
    assert b'title="Insert image"' in response.content
    assert b"btn-square text-base-content/70 hover:text-base-content" in response.content
    assert b'<span class="sr-only">Back to mail</span>' in response.content


def test_compose_send_requires_login(client: Client) -> None:
    response: Any = client.post(reverse("compose:send"), {"to": "alice@example.com"})

    assert response.status_code == 302


def test_compose_send_invalid_form_returns_422(logged_in_client: Client) -> None:
    response: Any = logged_in_client.post(reverse("compose:send"), {"to": ""})

    assert response.status_code == 422
    assert b"Enter at least one recipient." in response.content


def test_compose_send_delivers_message(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smtp = FakeSmtp()
    monkeypatch.setattr("apps.compose.views.get_mail_smtp_service", lambda request: smtp)

    response: Any = logged_in_client.post(
        reverse("compose:send"),
        {
            "to": "Alice <alice@example.com>",
            "cc": "carol@example.com",
            "subject": "Hello",
            "body": "Body text",
        },
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("mail:index")
    assert smtp.sent is not None
    sender, recipients, raw = smtp.sent
    assert sender == "user@example.com"
    assert recipients == ["alice@example.com", "carol@example.com"]
    assert b"Subject: Hello" in raw
    assert b"Body text" in raw


def test_compose_send_maps_auth_error_to_503(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RejectingSmtp:
        def __enter__(self) -> RejectingSmtp:
            raise SmtpAuthError("rejected")

        def __exit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(
        "apps.compose.views.get_mail_smtp_service",
        lambda request: RejectingSmtp(),
    )

    response: Any = logged_in_client.post(
        reverse("compose:send"),
        {"to": "alice@example.com", "subject": "Hello", "body": "Body"},
    )

    assert response.status_code == 503
    assert b"rejected the stored credentials" in response.content


def test_compose_reply_prefills_sender(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
    detail: MessageDetail,
) -> None:
    monkeypatch.setattr(
        "apps.compose.views.get_mail_imap_service",
        lambda request: FakeImapContext(),
    )
    monkeypatch.setattr("apps.compose.views.get_message", lambda imap, folder, uid: detail)

    response: Any = logged_in_client.get(
        reverse("compose:reply", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 200
    assert b'value="alice@example.com"' in response.content
    assert b'value="Re: Original subject"' in response.content


def test_compose_reply_all_prefills_recipients_and_cc(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    group_detail = MessageDetail(
        uid=7,
        folder="INBOX",
        subject="Group thread",
        sender="Alice <alice@example.com>",
        recipients="user@example.com, Bob <bob@example.com>",
        cc="Carol <carol@example.com>",
        date=datetime(2026, 10, 22, 10, 0, tzinfo=UTC),
        flags=(),
        is_seen=False,
        is_flagged=False,
        body_kind="plain",
        body_html="<p>Original body</p>",
        attachments=(),
        inline_cids={},
        remote_content_blocked=False,
    )
    monkeypatch.setattr(
        "apps.compose.views.get_mail_imap_service",
        lambda request: FakeImapContext(),
    )
    monkeypatch.setattr("apps.compose.views.get_message", lambda imap, folder, uid: group_detail)

    response: Any = logged_in_client.get(
        reverse("compose:reply_all", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 200
    assert b'value="alice@example.com, bob@example.com"' in response.content
    assert b'value="carol@example.com"' in response.content
    assert b'value="Re: Group thread"' in response.content


def test_compose_forward_prefills_quoted_body(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
    detail: MessageDetail,
) -> None:
    monkeypatch.setattr(
        "apps.compose.views.get_mail_imap_service",
        lambda request: FakeImapContext(),
    )
    monkeypatch.setattr("apps.compose.views.get_message", lambda imap, folder, uid: detail)

    response: Any = logged_in_client.get(
        reverse("compose:forward", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 200
    assert b'value="Fwd: Original subject"' in response.content
    assert b"Forwarded message" in response.content
    assert b"Original body" in response.content


def test_compose_reply_imap_error_returns_503(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(imap: Any, folder: str, uid: int) -> None:
        raise ImapConnectionError("down")

    monkeypatch.setattr(
        "apps.compose.views.get_mail_imap_service",
        lambda request: FakeImapContext(),
    )
    monkeypatch.setattr("apps.compose.views.get_message", fail)

    response: Any = logged_in_client.get(
        reverse("compose:reply", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 503
    assert b"Unable to load the message" in response.content


def test_compose_renders_attachment_input_and_autosave(logged_in_client: Client) -> None:
    response: Any = logged_in_client.get(reverse("compose:new"))

    assert response.status_code == 200
    assert b'name="attachments"' in response.content
    assert reverse("compose:attachments").encode() in response.content
    assert reverse("compose:draft").encode() in response.content


def test_compose_reply_does_not_autosave(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
    detail: MessageDetail,
) -> None:
    monkeypatch.setattr(
        "apps.compose.views.get_mail_imap_service",
        lambda request: FakeImapContext(),
    )
    monkeypatch.setattr("apps.compose.views.get_message", lambda imap, folder, uid: detail)

    response: Any = logged_in_client.get(
        reverse("compose:reply", kwargs={"folder_name": "INBOX", "uid": 7})
    )

    assert response.status_code == 200
    assert reverse("compose:draft").encode() not in response.content


def test_compose_upload_stores_attachment(logged_in_client: Client) -> None:
    response: Any = upload_attachment(logged_in_client)

    assert response.status_code == 200
    assert b"report.txt" in response.content
    assert b'name="attachment_ids"' in response.content
    refs = list_attachments(session_key(logged_in_client))
    assert len(refs) == 1
    assert refs[0].name == "report.txt"


def test_compose_upload_without_files_reports_error(logged_in_client: Client) -> None:
    response: Any = logged_in_client.post(reverse("compose:attachments"), {})

    assert response.status_code == 200
    assert b"Choose at least one file" in response.content


def test_compose_attachment_delete_removes_file(logged_in_client: Client) -> None:
    upload_attachment(logged_in_client)
    ref = list_attachments(session_key(logged_in_client))[0]

    response: Any = logged_in_client.post(
        reverse("compose:attachment_delete", kwargs={"attachment_id": ref.id})
    )

    assert response.status_code == 200
    assert b"report.txt" not in response.content
    assert list_attachments(session_key(logged_in_client)) == ()


def test_compose_draft_autosave_prefills_new_compose(logged_in_client: Client) -> None:
    response: Any = logged_in_client.post(
        reverse("compose:draft"),
        {
            "to": "alice@example.com",
            "cc": "carol@example.com",
            "subject": "Draft subject",
            "body": "Draft body",
        },
    )

    assert response.status_code == 204

    compose: Any = logged_in_client.get(reverse("compose:new"))
    assert b'value="alice@example.com"' in compose.content
    assert b'value="Draft subject"' in compose.content
    assert b"Draft body" in compose.content


def test_compose_empty_draft_clears_previous_text(logged_in_client: Client) -> None:
    save_draft(
        session_key(logged_in_client),
        to="alice@example.com",
        cc="",
        subject="Draft subject",
        body="Draft body",
    )

    logged_in_client.post(reverse("compose:draft"), {"to": "", "subject": "", "body": ""})

    compose: Any = logged_in_client.get(reverse("compose:new"))
    assert b'value="alice@example.com"' not in compose.content
    assert b'value="Draft subject"' not in compose.content


def test_compose_send_includes_attachments_and_clears_them(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_attachment(logged_in_client)
    ref = list_attachments(session_key(logged_in_client))[0]
    smtp = FakeSmtp()
    monkeypatch.setattr("apps.compose.views.get_mail_smtp_service", lambda request: smtp)

    response: Any = logged_in_client.post(
        reverse("compose:send"),
        {
            "to": "alice@example.com",
            "cc": "",
            "subject": "Hello",
            "body": "Body text",
            "attachment_ids": [ref.id],
        },
    )

    assert response.status_code == 302
    assert smtp.sent is not None
    _sender, _recipients, raw = smtp.sent
    assert b'filename="report.txt"' in raw
    assert list_attachments(session_key(logged_in_client)) == ()


def test_compose_invalid_send_keeps_attachments(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_attachment(logged_in_client)
    monkeypatch.setattr(
        "apps.compose.views.get_mail_smtp_service",
        lambda request: pytest.fail("SMTP must not be reached"),
    )

    response: Any = logged_in_client.post(
        reverse("compose:send"),
        {"to": "", "cc": "", "subject": "Hello", "body": "Body text"},
    )

    assert response.status_code == 422
    assert b"report.txt" in response.content
    assert len(list_attachments(session_key(logged_in_client))) == 1


def test_compose_new_prefills_account_signature_from_session(logged_in_client: Client) -> None:
    session = logged_in_client.session
    session["mail_signature"] = "Kind regards,\nAlice"
    session.save()

    response: Any = logged_in_client.get(reverse("compose:new"))

    assert response.status_code == 200
    assert b"Kind regards," in response.content


def test_compose_send_appends_copy_to_sent_folder(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smtp = FakeSmtp()
    appended: list[tuple[str, bytes]] = []

    class FakeSentImap:
        def __enter__(self) -> FakeSentImap:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def list_folders(self) -> list[Any]:
            from apps.accounts.services.imap import Folder

            return [Folder(name="Sent", delimiter="/", flags=("\\Sent",))]

        def append(self, folder: str, raw: bytes, **kwargs: object) -> None:
            appended.append((folder, raw))

    monkeypatch.setattr("apps.compose.views.get_mail_smtp_service", lambda request: smtp)
    monkeypatch.setattr(
        "apps.compose.views.get_mail_imap_service",
        lambda request: FakeSentImap(),
    )

    response: Any = logged_in_client.post(
        reverse("compose:send"),
        {"to": "alice@example.com", "cc": "", "subject": "Saved to sent", "body": "Body"},
    )

    assert response.status_code == 302
    assert len(appended) == 1
    assert appended[0][0] == "Sent"
    assert b"Subject: Saved to sent" in appended[0][1]


def test_compose_send_uses_session_display_name_in_from_header(
    logged_in_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smtp = FakeSmtp()
    monkeypatch.setattr("apps.compose.views.get_mail_smtp_service", lambda request: smtp)
    session = logged_in_client.session
    session["mail_display_name"] = "Alice Owner"
    session["mail_account_label"] = "Oficina"
    session.save()

    response: Any = logged_in_client.post(
        reverse("compose:send"),
        {"to": "bob@example.com", "cc": "", "subject": "Named sender", "body": "Hello"},
    )

    assert response.status_code == 302
    assert smtp.sent is not None
    envelope_sender, _recipients, raw = smtp.sent
    assert envelope_sender == "user@example.com"
    assert b"From: Alice Owner <user@example.com>" in raw
