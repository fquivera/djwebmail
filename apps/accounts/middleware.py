"""Middleware that hydrates the mail account from the server-side session."""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.accounts.services.session import activate_session_language, load_mail_account


class MailSessionMiddleware:
    """Attach ``request.mail_account`` and enforce absolute session expiry."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        setattr(request, "mail_account", load_mail_account(request))  # noqa: B010
        activate_session_language(request)
        return self.get_response(request)
