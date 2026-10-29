"""Context processors providing application metadata to templates."""

from __future__ import annotations

import datetime
from typing import Any

from django.http import HttpRequest

from apps.accounts.constants import SESSION_SERVER_ENGINE_KEY
from apps.mailadmin.models import CorporateIdentity
from apps.mailadmin.security import is_mail_admin
from common.version import get_djwebmail_version


def system_info(request: HttpRequest) -> dict[str, Any]:
    """Expose application version, IMAP server engine, copyright year, and corporate identity."""
    session = getattr(request, "session", None)
    server_engine = ""
    if session:
        engine_val = session.get(SESSION_SERVER_ENGINE_KEY)
        if isinstance(engine_val, str):
            server_engine = engine_val

    identity: CorporateIdentity | None = None
    try:
        identity = CorporateIdentity.get_solo()
    except Exception:
        pass

    return {
        "djwebmail_version": get_djwebmail_version(),
        "mail_server_engine": server_engine,
        "current_year": datetime.date.today().year,
        "is_mail_admin": is_mail_admin(request),
        "corporate_identity": identity,
    }
