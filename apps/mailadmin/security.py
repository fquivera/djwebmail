"""Security utilities and access control mixins for the mailadmin app."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, cast

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from apps.accounts.constants import SESSION_EMAIL_KEY

DENIED_MSG = "You do not have administrative privileges for this mail server."


def is_mail_admin(request: HttpRequest) -> bool:
    """Return whether the current request is authenticated as a mail administrator.

    Allowed callers:
    1. Django admin staff / superusers authenticated via standard Django auth.
    2. Webmail users whose email is listed in ``DJANGO_MAIL_ADMIN_ACCOUNTS``.
    """
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True

    session = getattr(request, "session", None)
    if session:
        email = session.get(SESSION_EMAIL_KEY)
        if isinstance(email, str) and email:
            admin_accounts: list[str] = getattr(settings, "MAIL_ADMIN_ACCOUNTS", [])
            if email.strip().lower() in admin_accounts:
                return True

    return False


class MailAdminRequiredMixin:
    """Class-based view mixin that enforces mail administrator privileges."""

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not is_mail_admin(request):
            session = getattr(request, "session", None)
            is_mail_user = bool(session and session.get(SESSION_EMAIL_KEY))
            user = getattr(request, "user", None)
            is_django_user = bool(user and getattr(user, "is_authenticated", False))

            if is_mail_user or is_django_user:
                raise PermissionDenied(DENIED_MSG)

            return redirect("accounts:login")

        return cast(HttpResponse, super().dispatch(request, *args, **kwargs))  # type: ignore[misc]


def mail_admin_required[F: Callable[..., HttpResponse]](view_func: F) -> F:
    """View decorator that enforces mail administrator privileges."""

    @functools.wraps(view_func)
    def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not is_mail_admin(request):
            session = getattr(request, "session", None)
            is_mail_user = bool(session and session.get(SESSION_EMAIL_KEY))
            user = getattr(request, "user", None)
            is_django_user = bool(user and getattr(user, "is_authenticated", False))

            if is_mail_user or is_django_user:
                raise PermissionDenied(DENIED_MSG)

            return redirect("accounts:login")

        return view_func(request, *args, **kwargs)

    return cast(F, _wrapped)
