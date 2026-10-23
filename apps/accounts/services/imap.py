"""IMAP connection and protocol operations.

The service is intentionally request-scoped: ``imapclient`` is not
thread-safe and a connection must never be shared through a module-level
singleton or cache.
"""

from __future__ import annotations

import imaplib
import ssl
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Any, TypeVar

from imapclient import IMAPClient
from imapclient.exceptions import (
    IMAPClientAbortError,
    IMAPClientError,
    LoginError,
    ProtocolError,
)

from apps.accounts.constants import (
    IMAP_FETCH_BATCH_SIZE,
    IMAP_SECURITY_NONE,
    IMAP_SECURITY_SSL,
    IMAP_SECURITY_STARTTLS,
    IMAP_SUMMARY_HEADER_FIELDS,
)
from apps.accounts.exceptions import (
    ImapAuthError,
    ImapConnectionError,
    ImapProtocolError,
)
from apps.accounts.services.account import MailAccount

T = TypeVar("T")
ClientFactory = Callable[..., Any]


@dataclass(frozen=True)
class Folder:
    """An IMAP folder as returned by LIST."""

    name: str
    delimiter: str
    flags: tuple[str, ...]


@dataclass(frozen=True)
class FolderStatus:
    """The subset of SELECT metadata used by the mail UI."""

    exists: int
    recent: int
    uid_validity: int | None
    uid_next: int | None
    flags: tuple[str, ...]
    permanent_flags: tuple[str, ...]
    read_only: bool


@dataclass(frozen=True)
class FetchedMessage:
    """A raw message body and its flags."""

    uid: int
    raw: bytes
    flags: tuple[str, ...]


@dataclass(frozen=True)
class FetchedSummary:
    """Message metadata fetched without loading the body."""

    uid: int
    headers: bytes
    flags: tuple[str, ...]
    size: int
    internaldate: datetime | None


class ImapService:
    """Connection-scoped IMAP client for one authenticated account."""

    def __init__(
        self,
        account: MailAccount,
        username: str,
        password: str,
        *,
        client_factory: ClientFactory = IMAPClient,
    ) -> None:
        self.account = account
        self.username = username
        self._password = password
        self._client_factory = client_factory
        self._client: Any | None = None

    def __enter__(self) -> ImapService:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def connect(self) -> None:
        """Open and authenticate the IMAP connection."""
        if self._client is not None:
            return

        context = ssl.create_default_context()
        if not self.account.verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        client: Any | None = None
        try:
            if self.account.imap_security == IMAP_SECURITY_SSL:
                client = self._client_factory(
                    self.account.imap_host,
                    port=self.account.imap_port,
                    ssl=True,
                    ssl_context=context,
                    timeout=self.account.timeout,
                )
            elif self.account.imap_security == IMAP_SECURITY_STARTTLS:
                client = self._client_factory(
                    self.account.imap_host,
                    port=self.account.imap_port,
                    ssl=False,
                    timeout=self.account.timeout,
                )
                assert client is not None
                client.starttls(ssl_context=context)
            elif self.account.imap_security == IMAP_SECURITY_NONE:
                client = self._client_factory(
                    self.account.imap_host,
                    port=self.account.imap_port,
                    ssl=False,
                    timeout=self.account.timeout,
                )
            else:  # pragma: no cover - MailAccount validates this first
                raise ImapConnectionError("Unsupported IMAP security mode")

            assert client is not None
            client.login(self.username, self._password)
        except LoginError as exc:
            self._logout_quietly(client)
            raise ImapAuthError("IMAP authentication failed") from exc
        except (OSError, TimeoutError, IMAPClientAbortError) as exc:
            self._logout_quietly(client)
            raise ImapConnectionError("Could not connect to the IMAP server") from exc
        except (IMAPClientError, ProtocolError, imaplib.IMAP4.error) as exc:
            self._logout_quietly(client)
            raise ImapProtocolError("The IMAP server returned an error") from exc

        self._client = client

    def close(self) -> None:
        """Close the connection without masking the caller's exception."""
        client = self._client
        self._client = None
        self._logout_quietly(client)

    def list_folders(self) -> list[Folder]:
        """Return folders visible to the authenticated account."""
        raw_folders = self._run(lambda: self._require_client().list_folders())
        return [
            Folder(
                name=_as_text(name),
                delimiter=_as_text(delimiter) if delimiter else "",
                flags=_as_flags(flags),
            )
            for flags, delimiter, name in raw_folders
        ]

    def select(self, folder: str, *, readonly: bool = False) -> FolderStatus:
        """Select a folder and return its status."""
        status = self._run(lambda: self._require_client().select_folder(folder, readonly=readonly))
        return FolderStatus(
            exists=_as_int(status.get(b"EXISTS", 0)),
            recent=_as_int(status.get(b"RECENT", 0)),
            uid_validity=_as_optional_int(status.get(b"UIDVALIDITY")),
            uid_next=_as_optional_int(status.get(b"UIDNEXT")),
            flags=_as_flags(status.get(b"FLAGS")),
            permanent_flags=_as_flags(status.get(b"PERMANENTFLAGS")),
            read_only=not bool(status.get(b"READ-WRITE", False)),
        )

    def search(self, criteria: Sequence[str] | str, *, charset: str = "UTF-8") -> list[int]:
        """Search the selected folder and return UIDs."""
        return self._run(lambda: self._require_client().search(criteria, charset=charset))

    def fetch_summaries(
        self,
        uids: Sequence[int],
        *,
        header_fields: Sequence[str] = IMAP_SUMMARY_HEADER_FIELDS,
        batch_size: int = IMAP_FETCH_BATCH_SIZE,
    ) -> list[FetchedSummary]:
        """Fetch headers, flags, size, and internal date for a set of UIDs."""
        if not uids:
            return []

        fields = " ".join(field.upper() for field in header_fields)
        selector = f"BODY.PEEK[HEADER.FIELDS ({fields})]"
        summaries: list[FetchedSummary] = []
        size = max(1, batch_size)

        for start in range(0, len(uids), size):
            batch = list(uids[start : start + size])
            response = self._run(
                lambda batch=batch: self._require_client().fetch(
                    batch,
                    [selector, "FLAGS", "INTERNALDATE", "RFC822.SIZE"],
                )
            )
            for uid in batch:
                record = response.get(uid)
                if not isinstance(record, dict):
                    continue
                headers_key = next(
                    (
                        key
                        for key in record
                        if isinstance(key, bytes) and key.upper().startswith(b"BODY[HEADER.FIELDS")
                    ),
                    None,
                )
                headers = record.get(headers_key, b"") if headers_key else b""
                if not isinstance(headers, bytes):
                    headers = b""
                raw_size = record.get(b"RFC822.SIZE")
                summaries.append(
                    FetchedSummary(
                        uid=uid,
                        headers=headers,
                        flags=_as_flags(record.get(b"FLAGS", ())),
                        size=_as_int(raw_size) if raw_size is not None else 0,
                        internaldate=_as_datetime(record.get(b"INTERNALDATE")),
                    )
                )

        return summaries

    def fetch_message(self, uid: int, *, peek: bool = True) -> FetchedMessage:
        """Fetch one raw message; PEEK avoids setting the ``\\Seen`` flag."""
        selector = "BODY.PEEK[]" if peek else "BODY[]"
        response = self._run(lambda: self._require_client().fetch([uid], [selector, "FLAGS"]))
        record = response.get(uid, {})
        raw = record.get(b"BODY[]")
        if not isinstance(raw, bytes):
            raise ImapProtocolError("The IMAP server returned no message body")
        return FetchedMessage(
            uid=uid,
            raw=raw,
            flags=_as_flags(record.get(b"FLAGS", ())),
        )

    def fetch_part(self, uid: int, part: str) -> bytes:
        """Fetch a single MIME part, for example ``1.2``."""
        selector = f"BODY.PEEK[{part}]"
        response = self._run(lambda: self._require_client().fetch([uid], [selector]))
        record = response.get(uid, {})
        raw = record.get(f"BODY[{part}]".encode())
        if not isinstance(raw, bytes):
            raise ImapProtocolError("The IMAP server returned no message part")
        return raw

    def store_flags(
        self,
        uids: Sequence[int],
        *,
        add: Sequence[str] = (),
        remove: Sequence[str] = (),
    ) -> None:
        """Add and/or remove flags on the selected folder's messages."""
        if add:
            self._run(lambda: self._require_client().add_flags(list(uids), list(add)))
        if remove:
            self._run(lambda: self._require_client().remove_flags(list(uids), list(remove)))

    def move(self, uids: Sequence[int], destination: str) -> None:
        """Move messages to another folder."""
        self._run(lambda: self._require_client().move(list(uids), destination))

    def copy(self, uids: Sequence[int], destination: str) -> None:
        """Copy messages to another folder."""
        self._run(lambda: self._require_client().copy(list(uids), destination))

    def delete(self, uids: Sequence[int], *, expunge: bool = False) -> None:
        """Mark messages deleted and optionally expunge them."""
        self._run(lambda: self._require_client().delete_messages(list(uids)))
        if expunge:
            self._run(lambda: self._require_client().expunge())

    def append(
        self,
        folder: str,
        raw: bytes,
        *,
        flags: Sequence[str] = (),
        when: datetime | None = None,
    ) -> None:
        """Append a raw message, used later for Sent and Drafts."""
        self._run(
            lambda: self._require_client().append(
                folder,
                raw,
                flags=list(flags),
                msg_time=when,
            )
        )

    def _require_client(self) -> Any:
        if self._client is None:
            self.connect()
        if self._client is None:  # pragma: no cover - connect either raises or sets it
            raise ImapConnectionError("The IMAP connection is not available")
        return self._client

    def _run(self, operation: Callable[[], T]) -> T:
        try:
            return operation()
        except LoginError as exc:
            raise ImapAuthError("IMAP authentication failed") from exc
        except (OSError, TimeoutError, IMAPClientAbortError) as exc:
            raise ImapConnectionError("The IMAP connection failed") from exc
        except (IMAPClientError, ProtocolError, imaplib.IMAP4.error) as exc:
            raise ImapProtocolError("The IMAP server returned an error") from exc

    @staticmethod
    def _logout_quietly(client: Any | None) -> None:
        if client is None:
            return
        with suppress(Exception):
            client.logout()


def _as_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _as_flags(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(_as_text(flag) for flag in value)


def _as_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, bytes):
        return int(value)
    return int(str(value))


def _as_optional_int(value: object | None) -> int | None:
    if value is None:
        return None
    return _as_int(value)


def _as_datetime(value: object | None) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return None
