"""Constants for the mailadmin application."""

from __future__ import annotations

DEFAULT_DIAGNOSTIC_TIMEOUT_SECONDS = 5  # hardcode-ok: safe diagnostic socket timeout in seconds
DEFAULT_DIAGNOSTIC_HELO_DOMAIN = (
    "localhost"  # hardcode-ok: standard loopback fallback domain for diagnostic EHLO handshake
)
