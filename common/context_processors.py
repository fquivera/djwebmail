"""Context processors providing application metadata to templates."""

from __future__ import annotations

import datetime
from typing import Any

from django.http import HttpRequest

from apps.accounts.constants import SESSION_SERVER_ENGINE_KEY
from common.version import get_djwebmail_version


def system_info(request: HttpRequest) -> dict[str, Any]:
    """Expose application version, IMAP server engine, and copyright year."""
    session = getattr(request, "session", None)
    server_engine = ""
    if session:
        engine_val = session.get(SESSION_SERVER_ENGINE_KEY)
        if isinstance(engine_val, str):
            server_engine = engine_val

    return {
        "djwebmail_version": get_djwebmail_version(),
        "mail_server_engine": server_engine,
        "current_year": datetime.date.today().year,
    }
