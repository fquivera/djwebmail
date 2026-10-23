"""Authorization helpers for webmail views.

Webmail authentication is independent from ``django.contrib.auth``; the mixin
checks the IMAP-backed session, not ``request.user``.
"""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse


class MailLoginRequiredMixin(AccessMixin):
    """Redirect anonymous mail users to the IMAP login page."""

    def dispatch(self, request: HttpRequest, *args: object, **kwargs: object) -> Any:
        if getattr(request, "mail_account", None) is None:
            return self.handle_no_permission()
        return cast(Any, super()).dispatch(request, *args, **kwargs)

    def handle_no_permission(self) -> HttpResponse:
        if getattr(self, "raise_exception", False):
            raise PermissionDenied(self.get_permission_denied_message())
        request = getattr(self, "request")  # noqa: B009
        return redirect_to_login(
            request.get_full_path(),
            self.get_login_url(),
            self.get_redirect_field_name(),
        )
