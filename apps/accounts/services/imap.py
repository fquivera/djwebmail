"""IMAP connection and protocol operations.

The service is intentionally request-scoped: ``imapclient`` is not
thread-safe and a connection must never be shared through a module-level
singleton or cache.
"""

from __future__ import annotations

import imaplib
import re
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


_ENGINE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\bDovecot(?:\s*\([^)]+\))?(?:\s+v?([0-9]+(?:\.[0-9]+)+(?:[-_a-zA-Z0-9]+)?))?",
            re.IGNORECASE,
        ),
        "Dovecot",
    ),
    (
        re.compile(
            r"\bGreenMail(?:\s+v?([0-9]+(?:\.[0-9]+)+(?:[-_a-zA-Z0-9]+)?))?",
            re.IGNORECASE,
        ),
        "GreenMail",
    ),
    (
        re.compile(
            r"\bCyrus(?:\s+IMAP)?(?:\s+v?([0-9]+(?:\.[0-9]+)+(?:[-_a-zA-Z0-9]+)?))?",
            re.IGNORECASE,
        ),
        "Cyrus IMAP",
    ),
    (
        re.compile(
            r"\bCourier(?:-IMAP)?(?:\s+v?([0-9]+(?:\.[0-9]+)+(?:[-_a-zA-Z0-9]+)?))?",
            re.IGNORECASE,
        ),
        "Courier-IMAP",
    ),
    (
        re.compile(
            r"\b(?:Microsoft\s+)?Exchange(?:\s+Server)?(?:\s+([0-9]{4}|[0-9]+(?:\.[0-9]+)*))?",
            re.IGNORECASE,
        ),
        "Microsoft Exchange",
    ),
    (
        re.compile(
            r"\bZimbra(?:\s+v?([0-9]+(?:\.[0-9]+)+(?:[-_a-zA-Z0-9]+)?))?",
            re.IGNORECASE,
        ),
        "Zimbra",
    ),
    (re.compile(r"\bGimap\b", re.IGNORECASE), "Gmail (Gimap)"),
)


def _normalize_id_data(raw: Any) -> dict[Any, Any]:
    """Safely convert IMAP ID response (dict, tuple or nested list) into a dict."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (tuple, list)):
        # If response is single-wrapped tuple/list like ((b'name', b'Dovecot', ...),)
        if len(raw) == 1 and isinstance(raw[0], (tuple, list)):
            raw = raw[0]
        # If it's a sequence of (key, value) pairs
        if all(isinstance(x, (tuple, list)) and len(x) == 2 for x in raw):
            return {k: v for k, v in raw}
        # If it's an alternating key-value sequence: (k1, v1, k2, v2, ...)
        items: dict[Any, Any] = {}
        for i in range(0, len(raw) - 1, 2):
            items[raw[i]] = raw[i + 1]
        return items
    return {}


def detect_imap_engine(
    welcome: bytes | str | None,
    id_data: Any | None = None,
) -> str:
    """Extract human-readable mail engine name and version from ID or greeting."""
    if id_data:
        try:
            norm_id = _normalize_id_data(id_data)
            name = ""
            version = ""
            for k, v in norm_id.items():
                k_str = _as_text(k).lower()
                v_str = _as_text(v)
                if k_str == "name":
                    name = v_str
                elif k_str == "version":
                    version = v_str
            if name:
                return f"{name} {version}".strip() if version else name
        except Exception:
            pass

    if not welcome:
        return "IMAP4rev1"

    text = _as_text(welcome)
    clean_text = re.sub(r"^\*\s+OK\s+(?:\[[^\]]*\]\s*)?", "", text, flags=re.IGNORECASE).strip()

    for pat, label in _ENGINE_PATTERNS:
        m = pat.search(clean_text)
        if m:
            ver = m.group(1) if m.lastindex and m.lastindex >= 1 else None
            return f"{label} {ver}" if ver else label

    if clean_text:
        first_part = clean_text.split(" ready")[0].split(" service")[0].strip()
        if 2 < len(first_part) < 40:
            return first_part

    return "IMAP4rev1"


class ImapService:
    """Connection-scoped IMAP client for one authenticated account."""

    def __init__(
        self,
        account: MailAccount,
        username: str,
        password: str,
        *,
        client_factory: ClientFactory = IMAPClient,
        on_connect: Callable[[str, str], None] | None = None,
    ) -> None:
        self.account = account
        self.username = username
        self._password = password
        self._client_factory = client_factory
        self._on_connect = on_connect
        self._client: Any | None = None
        self.server_engine: str = ""
        self.server_banner: str = ""

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
        welcome = getattr(client, "welcome", b"")
        id_data: Any | None = None
        if hasattr(client, "has_capability") and client.has_capability("ID"):
            with suppress(Exception):
                id_data = client.id_()

        try:
            self.server_engine = detect_imap_engine(welcome, id_data)
        except Exception:
            self.server_engine = "IMAP4rev1"
        self.server_banner = _as_text(welcome).strip()
        if self._on_connect:
            with suppress(Exception):
                self._on_connect(self.server_engine, self.server_banner)

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

    def search(
        self,
        criteria: Sequence[object] | str,
        *,
        charset: str | None = "UTF-8",
    ) -> list[int]:
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

    def create_folder(self, folder: str) -> None:
        """Create an IMAP folder when it does not exist yet."""
        self._run(lambda: self._require_client().create_folder(folder))

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
