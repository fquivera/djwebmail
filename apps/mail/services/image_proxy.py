"""Anti-SSRF image proxy.

Fetches a remote image on the user's behalf after the "load images" action and
streams it back as same-origin bytes. The webmail CSP allows ``img-src 'self'``
only, so the proxy is the sole way a remote image can reach the viewer.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from apps.mail.constants import (
    IMAGE_PROXY_ALLOWED_CONTENT_TYPES,
    IMAGE_PROXY_ALLOWED_SCHEMES,
)

_CHUNK_SIZE = 8192


class ImageProxyError(Exception):
    """The image could not be fetched safely."""


@dataclass(frozen=True)
class ProxiedImage:
    """Fetched image bytes and their validated content type."""

    content: bytes
    content_type: str


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Treat every redirect as terminal so it can be rejected explicitly."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def is_public_ip(value: str) -> bool:
    """Return True when ``value`` is a globally routable IP address."""
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def parse_proxy_url(value: str) -> tuple[str, str, int] | None:
    """Validate scheme/host and return ``(scheme, host, port)``, or None."""
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme.lower() not in IMAGE_PROXY_ALLOWED_SCHEMES:
        return None
    if not parts.hostname:
        return None
    port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    return parts.scheme.lower(), parts.hostname, port


def _resolves_to_public_host(host: str, port: int) -> bool:
    """Resolve ``host`` and require every address to be globally routable."""
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return False
    if not addresses:
        return False
    return all(is_public_ip(str(info[4][0])) for info in addresses)


def fetch_image(url: str, *, max_bytes: int, timeout: float) -> ProxiedImage:
    """Fetch and validate one image, raising :class:`ImageProxyError` on failure."""
    parsed = parse_proxy_url(url)
    if parsed is None:
        raise ImageProxyError("URL scheme or host is not allowed")
    scheme, host, port = parsed

    if not _resolves_to_public_host(host, port):
        raise ImageProxyError("URL resolves to a non-public address")

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "djwebmail-image-proxy", "Accept": "image/*"},
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        response = opener.open(request, timeout=timeout)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ImageProxyError("Could not fetch the image") from exc

    with response:
        if response.status not in (200,):
            raise ImageProxyError("Image responded with an unexpected status")
        content_type = _validate_content_type(response.headers.get_content_type())
        content = _read_limited(response, max_bytes)
    return ProxiedImage(content=content, content_type=content_type)


def _validate_content_type(content_type: str) -> str:
    normalized = content_type.split(";", 1)[0].strip().lower()
    if normalized not in IMAGE_PROXY_ALLOWED_CONTENT_TYPES:
        raise ImageProxyError("Image content type is not allowed")
    return normalized


def _read_limited(stream: Any, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ImageProxyError("Image exceeds the size limit")
        chunks.append(chunk)
    return b"".join(chunks)
