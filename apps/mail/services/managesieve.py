"""ManageSieve protocol client (RFC 5804).

Communicates with Dovecot Pigeonhole and Cyrus ManageSieve daemons to manage
Sieve mail filtering scripts.
"""

from __future__ import annotations

import base64
import re
import socket
import ssl
from typing import Any

from django.conf import settings

DEFAULT_MANAGESIEVE_PORT = 4190  # hardcode-ok: standard ManageSieve port RFC 5804


class ManageSieveError(Exception):
    """Base exception for ManageSieve protocol operations."""


class ManageSieveConnectionError(ManageSieveError):
    """Failed to connect to the ManageSieve server."""


class ManageSieveAuthError(ManageSieveError):
    """Authentication failed on the ManageSieve server."""


class ManageSieveProtocolError(ManageSieveError):
    """Unexpected protocol response from the ManageSieve server."""


class ManageSieveClient:
    """Synchronous RFC 5804 ManageSieve client."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_MANAGESIEVE_PORT,
        *,
        security: str = "starttls",
        timeout: int | None = None,
        verify_tls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.security = security.lower()
        self.timeout = timeout or getattr(settings, "MAIL_TIMEOUT_SECONDS", 30)
        self.verify_tls = verify_tls
        self.sock: socket.socket | ssl.SSLSocket | None = None
        self.file: Any = None
        self.capabilities: dict[str, str] = {}

    def __enter__(self) -> ManageSieveClient:
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def connect(self) -> None:
        """Connect to the ManageSieve host and parse initial capabilities."""
        try:
            raw_sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            if self.security == "ssl":
                ctx = ssl.create_default_context()
                if not self.verify_tls:
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                self.sock = ctx.wrap_socket(raw_sock, server_hostname=self.host)
            else:
                self.sock = raw_sock

            self.file = self.sock.makefile("rb")
            self._read_capabilities()

            if self.security == "starttls" and "STARTTLS" in self.capabilities:
                self._starttls()

        except OSError as exc:
            self.close()
            msg = f"Cannot connect to ManageSieve {self.host}:{self.port} - {exc}"
            raise ManageSieveConnectionError(msg) from exc

    def close(self) -> None:
        """Close socket and file streams."""
        if self.sock:
            try:
                self._send_line("LOGOUT")
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        self.file = None

    def _starttls(self) -> None:
        self._send_line("STARTTLS")
        res, msg = self._read_response()
        if res != "OK":
            raise ManageSieveProtocolError(f"STARTTLS failed: {msg}")

        ctx = ssl.create_default_context()
        if not self.verify_tls:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        assert self.sock is not None
        self.sock = ctx.wrap_socket(self.sock, server_hostname=self.host)
        self.file = self.sock.makefile("rb")
        self._read_capabilities()

    def _send_line(self, line: str) -> None:
        if not self.sock:
            raise ManageSieveConnectionError("Not connected")
        data = line.encode("utf-8") + b"\r\n"
        self.sock.sendall(data)

    def _read_line(self) -> str:
        if not self.file:
            raise ManageSieveConnectionError("Connection closed")
        line = self.file.readline()
        if not line:
            raise ManageSieveConnectionError("Server closed connection")
        return line.decode("utf-8", errors="replace").rstrip("\r\n")

    def _read_capabilities(self) -> None:
        self.capabilities.clear()
        while True:
            line = self._read_line()
            if not line:
                continue
            if line.startswith("OK"):
                break
            if line.startswith("NO") or line.startswith("BYE"):
                raise ManageSieveProtocolError(f"ManageSieve banner error: {line}")

            # Parse "CAPNAME" "VALUE" or "CAPNAME"
            match = re.match(r'^"([^"]+)"(?:\s+"([^"]*)")?', line)
            if match:
                cap = match.group(1).upper()
                val = match.group(2) or ""
                self.capabilities[cap] = val

    def _read_response(self) -> tuple[str, str]:
        """Read lines until OK, NO, or BYE is returned."""
        output_lines: list[str] = []
        while True:
            line = self._read_line()
            if line.startswith("OK"):
                return "OK", "\n".join(output_lines) or line
            elif line.startswith("NO"):
                return "NO", line
            elif line.startswith("BYE"):
                return "BYE", line
            else:
                output_lines.append(line)

    def authenticate(self, username: str, password: str) -> None:
        """Authenticate using SASL PLAIN mechanism."""
        sasl_caps = self.capabilities.get("SASL", "").upper()
        if "PLAIN" not in sasl_caps and sasl_caps:
            # Fall back to trying PLAIN anyway if unadvertised
            pass

        # PLAIN token: \0username\0password
        token = f"\0{username}\0{password}".encode()
        b64_token = base64.b64encode(token).decode("ascii")

        self._send_line(f'AUTHENTICATE "PLAIN" "{b64_token}"')
        res, msg = self._read_response()
        if res != "OK":
            raise ManageSieveAuthError(f"ManageSieve authentication failed: {msg}")

    def list_scripts(self) -> tuple[list[str], str | None]:
        """List all script names and identify the currently active script."""
        self._send_line("LISTSCRIPTS")
        scripts: list[str] = []
        active_script: str | None = None

        while True:
            line = self._read_line()
            if line.startswith("OK"):
                break
            elif line.startswith("NO") or line.startswith("BYE"):
                raise ManageSieveProtocolError(f"LISTSCRIPTS error: {line}")

            # Format: "name" [ACTIVE]
            match = re.match(r'^"([^"]+)"(\s+ACTIVE)?', line, re.IGNORECASE)
            if match:
                s_name = match.group(1)
                scripts.append(s_name)
                if match.group(2):
                    active_script = s_name

        return scripts, active_script

    def get_script(self, name: str) -> str:
        """Download script content by name."""
        self._send_line(f'GETSCRIPT "{name}"')
        content_lines: list[str] = []

        # First line contains string length or literal format, e.g. {123}
        header_line = self._read_line()
        length_match = re.search(r"\{(\d+)\+?\}", header_line)

        if length_match and self.file:
            length = int(length_match.group(1))
            bytes_data = self.file.read(length)
            content = bytes_data.decode("utf-8", errors="replace")
            # Consume trailing newline
            self._read_line()
        else:
            # Literal lines until OK
            content_lines.append(header_line)
            while True:
                line = self._read_line()
                if line.startswith("OK"):
                    break
                if line.startswith("NO"):
                    raise ManageSieveError(f"GETSCRIPT error: {line}")
                content_lines.append(line)
            content = "\n".join(content_lines)

        res, msg = self._read_response()
        if res != "OK":
            raise ManageSieveError(f"GETSCRIPT failed: {msg}")

        return content

    def put_script(self, name: str, content: str) -> None:
        """Upload a Sieve script to the server."""
        encoded = content.encode("utf-8")
        byte_len = len(encoded)

        # RFC 5804 string literal: {length+}
        self._send_line(f'PUTSCRIPT "{name}" {{{byte_len}+}}')
        assert self.sock is not None
        self.sock.sendall(encoded + b"\r\n")

        res, msg = self._read_response()
        if res != "OK":
            raise ManageSieveError(f"PUTSCRIPT failed: {msg}")

    def set_active(self, name: str) -> None:
        """Set a script active, or pass '' to deactivate all scripts."""
        self._send_line(f'SETACTIVE "{name}"')
        res, msg = self._read_response()
        if res != "OK":
            raise ManageSieveError(f"SETACTIVE failed: {msg}")

    def delete_script(self, name: str) -> None:
        """Delete a script on the server."""
        self._send_line(f'DELETESCRIPT "{name}"')
        res, msg = self._read_response()
        if res != "OK":
            raise ManageSieveError(f"DELETESCRIPT failed: {msg}")
