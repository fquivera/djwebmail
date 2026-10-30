"""Tests for the request-scoped IMAP service using a fake client."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from imapclient.exceptions import LoginError

from apps.accounts.exceptions import ImapAuthError, ImapConnectionError, ImapProtocolError
from apps.accounts.services.account import MailAccount
from apps.accounts.services.imap import ImapService, detect_imap_engine


class FakeClient:
    """Minimal IMAPClient double; no network and no implicit state."""

    def __init__(self) -> None:
        self.args: tuple[Any, ...] = ()
        self.kwargs: dict[str, Any] = {}
        self.logged_in: tuple[str, str] | None = None
        self.logged_out = False
        self.starttls_context: Any = None
        self.list_folders_result: list[tuple[tuple[bytes, ...], bytes, bytes]] = []
        self.select_result: dict[bytes, Any] = {}
        self.search_result: list[int] = []
        self.fetch_result: dict[int, dict[bytes, Any]] = {}
        self.fetch_calls: list[tuple[list[int], list[str]]] = []
        self.added_flags: tuple[list[int], list[str]] | None = None
        self.removed_flags: tuple[list[int], list[str]] | None = None
        self.moved: tuple[list[int], str] | None = None
        self.copied: tuple[list[int], str] | None = None
        self.deleted: list[int] | None = None
        self.expunged = False
        self.appended: tuple[str, bytes, list[str], Any] | None = None

    def login(self, username: str, password: str) -> None:
        self.logged_in = (username, password)

    def logout(self) -> None:
        self.logged_out = True

    def starttls(self, ssl_context: Any = None) -> None:
        self.starttls_context = ssl_context

    def list_folders(self) -> list[tuple[tuple[bytes, ...], bytes, bytes]]:
        return self.list_folders_result

    def select_folder(self, folder: str, readonly: bool = False) -> dict[bytes, Any]:
        return self.select_result

    def search(self, criteria: Any, charset: str | None = None) -> list[int]:
        return self.search_result

    def fetch(self, messages: list[int], data: list[str]) -> dict[int, dict[bytes, Any]]:
        self.fetch_calls.append((messages, data))
        return self.fetch_result

    def add_flags(self, messages: list[int], flags: list[str]) -> None:
        self.added_flags = (messages, flags)

    def remove_flags(self, messages: list[int], flags: list[str]) -> None:
        self.removed_flags = (messages, flags)

    def move(self, messages: list[int], folder: str) -> None:
        self.moved = (messages, folder)

    def copy(self, messages: list[int], folder: str) -> None:
        self.copied = (messages, folder)

    def delete_messages(self, messages: list[int]) -> None:
        self.deleted = messages

    def expunge(self) -> None:
        self.expunged = True

    def append(
        self,
        folder: str,
        msg: bytes,
        flags: list[str] | None = None,
        msg_time: Any = None,
    ) -> None:
        self.appended = (folder, msg, flags or [], msg_time)


def factory_for(client: FakeClient) -> Callable[..., FakeClient]:
    def factory(*args: Any, **kwargs: Any) -> FakeClient:
        client.args = args
        client.kwargs = kwargs
        return client

    return factory


@pytest.fixture
def account() -> MailAccount:
    return MailAccount(
        email="user@example.com",
        domain="example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_security="ssl",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_security="starttls",
        verify_tls=True,
        timeout=30,
    )


def test_connect_uses_ssl_and_logs_in(account: MailAccount) -> None:
    client = FakeClient()
    service = ImapService(account, "user@example.com", "secret", client_factory=factory_for(client))

    service.connect()

    assert client.args == ("imap.example.com",)
    assert client.kwargs["port"] == 993
    assert client.kwargs["ssl"] is True
    assert client.kwargs["timeout"] == 30
    assert client.logged_in == ("user@example.com", "secret")
    assert client.starttls_context is None


def test_connect_uses_starttls(account: MailAccount) -> None:
    client = FakeClient()
    account = MailAccount(
        email=account.email,
        domain=account.domain,
        imap_host=account.imap_host,
        imap_port=account.imap_port,
        imap_security="starttls",
        smtp_host=account.smtp_host,
        smtp_port=account.smtp_port,
        smtp_security=account.smtp_security,
    )
    service = ImapService(account, "user@example.com", "secret", client_factory=factory_for(client))

    service.connect()

    assert client.kwargs["ssl"] is False
    assert client.starttls_context is not None
    assert client.logged_in is not None


def test_connect_maps_authentication_failure(account: MailAccount) -> None:
    class AuthFailClient(FakeClient):
        def login(self, username: str, password: str) -> None:
            raise LoginError("bad credentials")

    client = AuthFailClient()
    service = ImapService(account, "user@example.com", "secret", client_factory=factory_for(client))

    with pytest.raises(ImapAuthError):
        service.connect()

    assert client.logged_out is True


def test_connect_maps_connection_failure(account: MailAccount) -> None:
    def factory(*args: Any, **kwargs: Any) -> FakeClient:
        raise OSError("unreachable")

    service = ImapService(account, "user@example.com", "secret", client_factory=factory)

    with pytest.raises(ImapConnectionError):
        service.connect()


def test_context_manager_closes_connection(account: MailAccount) -> None:
    client = FakeClient()
    with ImapService(account, "user@example.com", "secret", client_factory=factory_for(client)):
        pass

    assert client.logged_out is True


def test_list_folders_and_select(account: MailAccount) -> None:
    client = FakeClient()
    client.list_folders_result = [((b"\\HasNoChildren",), b"/", b"INBOX")]
    client.select_result = {
        b"EXISTS": 3,
        b"RECENT": 1,
        b"UIDVALIDITY": 42,
        b"UIDNEXT": 9,
        b"FLAGS": (b"\\Seen", b"\\Flagged"),
        b"PERMANENTFLAGS": (b"\\Seen",),
        b"READ-WRITE": True,
    }
    service = ImapService(account, "user@example.com", "secret", client_factory=factory_for(client))

    folders = service.list_folders()
    status = service.select("INBOX")

    assert folders[0].name == "INBOX"
    assert folders[0].delimiter == "/"
    assert folders[0].flags == ("\\HasNoChildren",)
    assert status.exists == 3
    assert status.recent == 1
    assert status.uid_validity == 42
    assert status.uid_next == 9
    assert status.read_only is False


def test_fetch_message_and_part(account: MailAccount) -> None:
    client = FakeClient()
    client.fetch_result = {
        7: {b"BODY[]": b"raw message", b"FLAGS": (b"\\Seen",)},
        8: {b"BODY[1.2]": b"part body"},
    }
    service = ImapService(account, "user@example.com", "secret", client_factory=factory_for(client))

    message = service.fetch_message(7)
    part = service.fetch_part(8, "1.2")

    assert message.raw == b"raw message"
    assert message.flags == ("\\Seen",)
    assert part == b"part body"


def test_fetch_without_body_raises_protocol_error(account: MailAccount) -> None:
    client = FakeClient()
    client.fetch_result = {7: {b"FLAGS": ()}}
    service = ImapService(account, "user@example.com", "secret", client_factory=factory_for(client))

    with pytest.raises(ImapProtocolError):
        service.fetch_message(7)


def test_flag_move_copy_delete_and_append(account: MailAccount) -> None:
    client = FakeClient()
    service = ImapService(account, "user@example.com", "secret", client_factory=factory_for(client))

    service.store_flags([1, 2], add=["\\Seen"], remove=["\\Flagged"])
    service.move([1], "Archive")
    service.copy([2], "Archive")
    service.delete([1, 2], expunge=True)
    service.append("Sent", b"raw", flags=["\\Seen"])

    assert client.added_flags == ([1, 2], ["\\Seen"])
    assert client.removed_flags == ([1, 2], ["\\Flagged"])
    assert client.moved == ([1], "Archive")
    assert client.copied == ([2], "Archive")
    assert client.deleted == [1, 2]
    assert client.expunged is True
    assert client.appended is not None
    assert client.appended[0] == "Sent"


def test_fetch_summaries_without_body(account: MailAccount) -> None:
    internaldate = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)
    client = FakeClient()
    client.fetch_result = {
        7: {
            b"BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)]": (
                b"From: Alice <alice@example.com>\r\nSubject: Hello\r\n\r\n"
            ),
            b"FLAGS": (b"\\Seen",),
            b"RFC822.SIZE": 123,
            b"INTERNALDATE": internaldate,
        }
    }
    service = ImapService(account, "user@example.com", "secret", client_factory=factory_for(client))

    summaries = service.fetch_summaries([7])

    assert len(summaries) == 1
    assert summaries[0].uid == 7
    assert b"Subject: Hello" in summaries[0].headers
    assert summaries[0].flags == ("\\Seen",)
    assert summaries[0].size == 123
    assert summaries[0].internaldate == internaldate
    assert client.fetch_calls[0][0] == [7]
    assert client.fetch_calls[0][1][0].startswith("BODY.PEEK[HEADER.FIELDS")


def test_fetch_summaries_batches_uids(account: MailAccount) -> None:
    client = FakeClient()
    client.fetch_result = {
        1: {b"FLAGS": (), b"RFC822.SIZE": 1},
        2: {b"FLAGS": (), b"RFC822.SIZE": 2},
    }
    service = ImapService(account, "user@example.com", "secret", client_factory=factory_for(client))

    summaries = service.fetch_summaries([1, 2], batch_size=1)

    assert [summary.uid for summary in summaries] == [1, 2]
    assert [call[0] for call in client.fetch_calls] == [[1], [2]]


def test_fetch_summaries_empty_does_not_connect(account: MailAccount) -> None:
    service = ImapService(account, "user@example.com", "secret")

    assert service.fetch_summaries([]) == []


def test_detect_imap_engine_from_id_data() -> None:
    id_data = {b"name": b"Dovecot", b"version": b"2.4.1"}
    assert detect_imap_engine(b"", id_data) == "Dovecot 2.4.1"

    id_data_no_ver = {b"name": b"Cyrus"}
    assert detect_imap_engine(b"", id_data_no_ver) == "Cyrus"

    # IMAPClient parse_response returns tuples for Dovecot/RFC 2971 responses
    id_data_nested_tuple = ((b"name", b"Dovecot", b"version", b"2.3.21"),)
    assert detect_imap_engine(b"", id_data_nested_tuple) == "Dovecot 2.3.21"

    id_data_flat_tuple = (b"name", b"Dovecot", b"version", b"2.3.21")
    assert detect_imap_engine(b"", id_data_flat_tuple) == "Dovecot 2.3.21"

    id_data_pairs_tuple = ((b"name", b"Dovecot"), (b"version", b"2.3.21"))
    assert detect_imap_engine(b"", id_data_pairs_tuple) == "Dovecot 2.3.21"

    # Malformed ID data should not crash and should fall back safely
    assert detect_imap_engine(b"* OK GreenMail ready", (123,)) == "GreenMail"


def test_detect_imap_engine_from_banners() -> None:
    assert detect_imap_engine(b"* OK [CAPABILITY IMAP4rev1] Dovecot (Debian) ready.") == "Dovecot"
    assert (
        detect_imap_engine(b"* OK [CAPABILITY IMAP4rev1] Dovecot 2.3.16 ready.") == "Dovecot 2.3.16"
    )
    assert detect_imap_engine(b"* OK GreenMail IMAP4rev1 service ready.") == "GreenMail"
    assert (
        detect_imap_engine(b"* OK [CAPABILITY IMAP4rev1] Cyrus IMAP 3.4.1 ready.")
        == "Cyrus IMAP 3.4.1"
    )
    assert (
        detect_imap_engine(b"* OK [CAPABILITY IMAP4rev1] Courier-IMAP 5.1.0 ready.")
        == "Courier-IMAP 5.1.0"
    )
    assert (
        detect_imap_engine(b"* OK Microsoft Exchange Server 2019 IMAP4 service ready.")
        == "Microsoft Exchange 2019"
    )
    assert detect_imap_engine(b"* OK Zimbra 8.8.15 ready.") == "Zimbra 8.8.15"
    assert detect_imap_engine(b"* OK Gimap ready for requests from 192.0.2.1") == "Gmail (Gimap)"
    assert detect_imap_engine(b"* OK CustomMail 1.0 ready.") == "CustomMail 1.0"
    assert detect_imap_engine(b"") == "IMAP4rev1"
    assert detect_imap_engine(None) == "IMAP4rev1"


def test_imap_service_detects_engine_and_invokes_callback(account: MailAccount) -> None:
    client = FakeClient()
    setattr(client, "welcome", b"* OK GreenMail IMAP4rev1 service ready.")  # noqa: B010
    captured: list[tuple[str, str]] = []

    def on_connect(engine: str, banner: str) -> None:
        captured.append((engine, banner))

    service = ImapService(
        account,
        "user@example.com",
        "secret",
        client_factory=factory_for(client),
        on_connect=on_connect,
    )
    with service:
        assert service.server_engine == "GreenMail"
        assert "* OK GreenMail" in service.server_banner

    assert len(captured) == 1
    assert captured[0][0] == "GreenMail"
    assert "* OK GreenMail" in captured[0][1]
