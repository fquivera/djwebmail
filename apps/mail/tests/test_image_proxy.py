"""Tests for the anti-SSRF image proxy."""

from __future__ import annotations

import pytest

from apps.mail.services.image_proxy import (
    ImageProxyError,
    _read_limited,
    _validate_content_type,
    fetch_image,
    is_public_ip,
    parse_proxy_url,
)


class FakeStream:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def read(self, size: int) -> bytes:
        chunk = self._data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk


def test_parse_proxy_url_accepts_http_and_https() -> None:
    assert parse_proxy_url("https://example.com/x.png") == ("https", "example.com", 443)
    assert parse_proxy_url("http://example.com:8080/x.png") == ("http", "example.com", 8080)


def test_parse_proxy_url_rejects_bad_schemes_and_hosts() -> None:
    assert parse_proxy_url("javascript:alert(1)") is None
    assert parse_proxy_url("file:///etc/passwd") is None
    assert parse_proxy_url("ftp://example.com/x.png") is None
    assert parse_proxy_url("https://") is None


@pytest.mark.parametrize(
    "value",
    ["127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.0.1", "169.254.1.1", "::1", "fe80::1"],
)
def test_is_public_ip_rejects_private_and_reserved(value: str) -> None:
    assert is_public_ip(value) is False


@pytest.mark.parametrize("value", ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"])
def test_is_public_ip_accepts_public_addresses(value: str) -> None:
    assert is_public_ip(value) is True


def test_fetch_image_rejects_bad_scheme() -> None:
    with pytest.raises(ImageProxyError):
        fetch_image("file:///etc/passwd", max_bytes=1024, timeout=1)


def test_fetch_image_rejects_private_host_before_connecting() -> None:
    with pytest.raises(ImageProxyError):
        fetch_image("http://127.0.0.1/x.png", max_bytes=1024, timeout=1)


def test_read_limited_enforces_size_limit() -> None:
    with pytest.raises(ImageProxyError):
        _read_limited(FakeStream(b"x" * 100), max_bytes=10)


def test_read_limited_returns_full_stream() -> None:
    assert _read_limited(FakeStream(b"abc"), max_bytes=10) == b"abc"


def test_validate_content_type_allowlist() -> None:
    assert _validate_content_type("image/png") == "image/png"
    assert _validate_content_type("IMAGE/JPEG; charset=binary") == "image/jpeg"

    with pytest.raises(ImageProxyError):
        _validate_content_type("image/svg+xml")
    with pytest.raises(ImageProxyError):
        _validate_content_type("text/html")
