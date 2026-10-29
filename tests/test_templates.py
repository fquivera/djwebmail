"""Template-level guards for the Tailwind/daisyUI and HTMX contracts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from django.conf import settings
from django.test import Client
from django.urls import reverse


def _project_templates() -> list[Path]:
    roots = [settings.BASE_DIR / "templates", settings.BASE_DIR / "apps"]
    return sorted(path for root in roots for path in root.rglob("*.html"))


def test_templates_avoid_inline_styles_and_htmx_eval() -> None:
    for path in _project_templates():
        source = path.read_text(encoding="utf-8")
        assert 'style="' not in source, f"inline style found in {path}"
        assert "hx-on" not in source, f"hx-on found in {path}"
        assert 'hx-vals="js:' not in source, f"javascript hx-vals found in {path}"
        assert not re.search(r'hx-[a-z-]+="[^"]*\[[^"]*\]', source), (
            f"HTMX filter expression found in {path}"
        )
        assert not re.search(r"<script(?![^>]*\bsrc=)", source), f"inline script found in {path}"


def test_base_template_loads_compiled_tailwind_css(client: Client) -> None:
    response: Any = client.get(reverse("home"))

    assert response.status_code == 200
    assert b"css/dist/styles.css" in response.content
    assert b"css/app.css" not in response.content


def test_base_template_renders_footer_and_about_dialog(client: Client) -> None:
    response: Any = client.get(reverse("home"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "DjWebmail" in content
    assert "about-dialog" in content
    assert 'data-dialog-open="about-dialog"' in content
    assert "js/dialog.js" in content
    assert "<dialog" in content
    assert "sticky" in content
    assert "bottom-0" in content
