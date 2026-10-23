"""Authentication decorators for webmail views."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


def login_redirect(request: HttpRequest) -> HttpResponse:
    """Send the user to the login page and preserve the current destination."""
    query = urlencode({"next": request.get_full_path()})
    target = f"{reverse('accounts:login')}?{query}"
    if request.META.get("HTTP_HX_REQUEST") == "true":
        # A normal 302 would make HTMX swap the login page into the mail target.
        return HttpResponse(status=204, headers={"HX-Redirect": target})
    return redirect(target)


def mail_login_required(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """Redirect anonymous requests to the IMAP login page with a safe ``next``."""

    @wraps(view)
    def wrapped(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if getattr(request, "mail_account", None) is None:
            return login_redirect(request)
        return view(request, *args, **kwargs)

    return wrapped
