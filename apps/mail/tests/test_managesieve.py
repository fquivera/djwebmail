"""Unit tests for ManageSieve protocol client (RFC 5804)."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from apps.mail.services.managesieve import (
    ManageSieveAuthError,
    ManageSieveClient,
    ManageSieveConnectionError,
)


class FakeSocket:
    def __init__(self, responses: list[bytes]) -> None:
        self.sent_bytes = io.BytesIO()
        self.read_bytes = io.BytesIO(b"".join(responses))

    def makefile(self, mode: str = "rb"):
        return self.read_bytes

    def sendall(self, data: bytes) -> None:
        self.sent_bytes.write(data)

    def close(self) -> None:
        pass


def test_managesieve_connect_and_parse_capabilities():
    banner_responses = [
        b'"IMPLEMENTATION" "Dovecot Pigeonhole"\r\n',
        b'"SIEVE" "fileinto reject vacation"\r\n',
        b'"SASL" "PLAIN"\r\n',
        b'OK "Dovecot ready."\r\n',
    ]
    fake_sock = FakeSocket(banner_responses)

    with patch("socket.create_connection", return_value=fake_sock):
        client = ManageSieveClient(host="mail.example.com", port=4190, security="none")
        client.connect()

        assert client.capabilities["IMPLEMENTATION"] == "Dovecot Pigeonhole"
        assert client.capabilities["SASL"] == "PLAIN"
        assert "fileinto" in client.capabilities["SIEVE"]
        client.close()


def test_managesieve_auth_success():
    responses = [
        b'"IMPLEMENTATION" "Dovecot Pigeonhole"\r\n',
        b'"SASL" "PLAIN"\r\n',
        b'OK "Dovecot ready."\r\n',
        b'OK "Logged in."\r\n',
    ]
    fake_sock = FakeSocket(responses)

    with patch("socket.create_connection", return_value=fake_sock):
        client = ManageSieveClient(host="mail.example.com", security="none")
        client.connect()
        client.authenticate("user@example.com", "secret123")

        sent_data = fake_sock.sent_bytes.getvalue().decode()
        assert 'AUTHENTICATE "PLAIN"' in sent_data
        client.close()


def test_managesieve_auth_failure_raises_error():
    responses = [
        b'"IMPLEMENTATION" "Dovecot Pigeonhole"\r\n',
        b'OK "Dovecot ready."\r\n',
        b'NO "Authentication failed."\r\n',
    ]
    fake_sock = FakeSocket(responses)

    with patch("socket.create_connection", return_value=fake_sock):
        client = ManageSieveClient(host="mail.example.com", security="none")
        client.connect()
        with pytest.raises(ManageSieveAuthError, match="Authentication failed"):
            client.authenticate("user@example.com", "wrong")
        client.close()


def test_managesieve_list_scripts():
    responses = [
        b'OK "Dovecot ready."\r\n',
        b'"old_rules"\r\n',
        b'"djwebmail" ACTIVE\r\n',
        b'OK "Listscripts completed."\r\n',
    ]
    fake_sock = FakeSocket(responses)

    with patch("socket.create_connection", return_value=fake_sock):
        client = ManageSieveClient(host="mail.example.com", security="none")
        client.connect()
        scripts, active = client.list_scripts()

        assert scripts == ["old_rules", "djwebmail"]
        assert active == "djwebmail"
        client.close()


def test_managesieve_get_and_put_script():
    script_body = b'require ["fileinto"];\nfileinto "Archive";\n'
    length = len(script_body)
    responses = [
        b'OK "Dovecot ready."\r\n',
        f"{{{length}+}}\r\n".encode() + script_body + b'\r\nOK "Getscript completed."\r\n',
        b'OK "Putscript completed."\r\n',
        b'OK "Setactive completed."\r\n',
    ]
    fake_sock = FakeSocket(responses)

    with patch("socket.create_connection", return_value=fake_sock):
        client = ManageSieveClient(host="mail.example.com", security="none")
        client.connect()

        content = client.get_script("djwebmail")
        assert 'fileinto "Archive";' in content

        client.put_script("djwebmail", 'require ["fileinto"];\n')
        client.set_active("djwebmail")

        sent_data = fake_sock.sent_bytes.getvalue().decode()
        assert 'PUTSCRIPT "djwebmail"' in sent_data
        assert 'SETACTIVE "djwebmail"' in sent_data
        client.close()


def test_managesieve_connection_refused_raises_error():
    err = ConnectionRefusedError("Connection refused")
    with patch("socket.create_connection", side_effect=err):
        client = ManageSieveClient(host="offline.example.com", security="none")
        with pytest.raises(ManageSieveConnectionError, match="Cannot connect"):
            client.connect()
