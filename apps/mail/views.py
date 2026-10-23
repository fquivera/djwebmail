"""Folder tree and message list views."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_headers

from apps.accounts.decorators import login_redirect, mail_login_required
from apps.accounts.exceptions import ImapAuthError, MailError, MailSessionError
from apps.accounts.services.session import end_mail_session, get_mail_imap_service
from apps.mail.constants import IMAP_INBOX
from apps.mail.services.mailbox import list_folders, list_messages
from apps.mail.services.message import get_message


@never_cache
@vary_on_headers("HX-Request")
@mail_login_required
def mailbox(request: HttpRequest, folder_name: str = IMAP_INBOX) -> HttpResponse:
    """Render the mail shell or a message-list fragment for one folder."""
    folder = folder_name or IMAP_INBOX
    page_value = request.GET.get("page")
    page_number = _parse_page(page_value if isinstance(page_value, str) else None)
    page_size = min(
        max(1, settings.MAIL_DEFAULT_PAGE_SIZE),
        max(1, settings.MAIL_MAX_PAGE_SIZE),
    )

    try:
        with get_mail_imap_service(request) as imap:
            folders = list_folders(imap)
            page = list_messages(imap, folder, page=page_number, page_size=page_size)
    except MailSessionError:
        return login_redirect(request)
    except ImapAuthError:
        end_mail_session(request)
        return login_redirect(request)
    except MailError:
        return _error_response(request)

    context = {
        "folder_name": folder,
        "folders": folders,
        "page": page,
    }
    if request.META.get("HTTP_HX_REQUEST") == "true":
        return render(request, "mail/_mailbox_response.html", context)
    return render(request, "mail/index.html", context)


@never_cache
@vary_on_headers("HX-Request")
@mail_login_required
def message_view(request: HttpRequest, folder_name: str, uid: int) -> HttpResponse:
    """Render one sanitized message as a viewer fragment or a full page."""
    folder = folder_name or IMAP_INBOX
    try:
        with get_mail_imap_service(request) as imap:
            message = get_message(imap, folder, uid)
    except MailSessionError:
        return login_redirect(request)
    except ImapAuthError:
        end_mail_session(request)
        return login_redirect(request)
    except MailError:
        return _error_response(request)

    context = {
        "folder_name": folder,
        "message": message,
    }
    if request.META.get("HTTP_HX_REQUEST") == "true":
        return render(request, "mail/_message_view.html", context)
    return render(request, "mail/message.html", context)


def _parse_page(value: str | None) -> int:
    try:
        page = int(value or "1")
    except (TypeError, ValueError):
        return 1
    return max(1, page)


def _error_response(request: HttpRequest) -> HttpResponse:
    context = {"error": _("Unable to load mail. Try again later.")}
    if request.META.get("HTTP_HX_REQUEST") == "true":
        # HTMX swaps 2xx responses; keep the error visible in the list target.
        return render(request, "mail/_error.html", context)
    return render(request, "mail/error.html", context, status=503)
