"""SMTP connection and message delivery.

Like :class:`~apps.accounts.services.imap.ImapService`, this service is
request-scoped: one connection per authenticated mail session, never shared.
The password is the same encrypted credential used for IMAP and never leaves
the server.
"""

from __future__ import annotations

import smtplib
import ssl
from collections.abc import Callable, Sequence
from contextlib import suppress
from types import TracebackType
from typing import Any

from apps.accounts.constants import SMTP_SECURITY_SSL, SMTP_SECURITY_STARTTLS
from apps.accounts.exceptions import (
    SmtpAuthError,
    SmtpConnectionError,
    SmtpSendError,
)
from apps.accounts.services.account import MailAccount

ClientFactory = Callable[..., Any]


class SmtpService:
    """Connection-scoped SMTP client for one authenticated account."""

    def __init__(
        self,
        account: MailAccount,
        username: str,
        password: str,
        *,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.account = account
        self.username = username
        self._password = password
        self._client_factory = client_factory
        self._client: Any | None = None

    def __enter__(self) -> SmtpService:
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
        """Open the SMTP connection and authenticate when possible."""
        if self._client is not None:
            return

        context = self._tls_context()
        client: Any | None = None
        try:
            client = self._new_client(context)
            if client is None:
                raise SmtpConnectionError("The SMTP client could not be created")
            if self.account.smtp_security == SMTP_SECURITY_STARTTLS:
                client.starttls(context=context)
                client.ehlo()
            if self._password:
                client.login(self.username, self._password)
        except smtplib.SMTPAuthenticationError as exc:
            self._close_quietly(client)
            raise SmtpAuthError("SMTP authentication failed") from exc
        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            self._close_quietly(client)
            raise SmtpConnectionError("Could not connect to the SMTP server") from exc

        self._client = client

    def send(self, sender: str, recipients: Sequence[str], raw: bytes) -> None:
        """Deliver one raw RFC 5322 message to every recipient."""
        client = self._require_client()
        try:
            client.sendmail(sender, list(recipients), raw)
        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            raise SmtpSendError("The SMTP server rejected the message") from exc

    def close(self) -> None:
        """Log out and drop the connection."""
        if self._client is None:
            return
        with suppress(smtplib.SMTPException, OSError):
            self._client.quit()
        self._client = None

    def _new_client(self, context: ssl.SSLContext) -> Any:
        if self._client_factory is not None:
            return self._client_factory(
                self.account.smtp_host,
                self.account.smtp_port,
                timeout=self.account.timeout,
                context=context,
            )
        if self.account.smtp_security == SMTP_SECURITY_SSL:
            return smtplib.SMTP_SSL(
                self.account.smtp_host,
                self.account.smtp_port,
                timeout=self.account.timeout,
                context=context,
            )
        return smtplib.SMTP(
            self.account.smtp_host,
            self.account.smtp_port,
            timeout=self.account.timeout,
        )

    def _tls_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context()
        if not self.account.verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context

    def _require_client(self) -> Any:
        if self._client is None:
            self.connect()
        if self._client is None:  # pragma: no cover - connect either raises or sets it
            raise SmtpConnectionError("The SMTP connection is not available")
        return self._client

    @staticmethod
    def _close_quietly(client: Any | None) -> None:
        if client is None:
            return
        with suppress(smtplib.SMTPException, OSError):
            client.close()


__all__ = ["SmtpService"]
