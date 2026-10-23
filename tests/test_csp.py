"""Tests for the strict webmail Content-Security-Policy."""

from __future__ import annotations

from typing import Any

from django.test import Client
from django.urls import reverse


def test_webmail_emits_strict_csp(client: Client) -> None:
    response: Any = client.get(reverse("home"))

    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "unsafe-eval" not in csp
    assert "unsafe-inline" not in csp
    assert "style-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    # Remote images are blocked: the viewer never loads them directly.
    assert "https:" not in csp
    assert "img-src 'self' data: blob:" in csp


def test_admin_is_excluded_from_webmail_csp(client: Client) -> None:
    response: Any = client.get("/admin/login/")

    assert response.status_code == 200
    assert "Content-Security-Policy" not in response


def test_webmail_sets_clickjacking_and_sniffing_headers(client: Client) -> None:
    response: Any = client.get(reverse("home"))

    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
