"""Folder tree and message list views."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers

from apps.accounts.decorators import login_redirect, mail_login_required
from apps.accounts.exceptions import ImapAuthError, MailError, MailSessionError
from apps.accounts.services.session import end_mail_session, get_mail_imap_service
from apps.mail.constants import IMAP_INBOX
from apps.mail.services.image_proxy import ImageProxyError, fetch_image
from apps.mail.services.mailbox import list_folders, list_messages
from apps.mail.services.message import get_message, proxy_remote_images


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


@never_cache
@require_POST
@mail_login_required
def message_remote_images(
    request: HttpRequest,
    folder_name: str,
    uid: int,
) -> HttpResponse:
    """Re-render the body with remote images proxied through the same origin."""
    folder = folder_name or IMAP_INBOX
    try:
        with get_mail_imap_service(request) as imap:
            message = get_message(imap, folder, uid, allow_images=True)
    except MailSessionError:
        return login_redirect(request)
    except ImapAuthError:
        end_mail_session(request)
        return login_redirect(request)
    except MailError:
        return _error_response(request)

    body_html = proxy_remote_images(message.body_html, reverse("mail:image_proxy"))
    return render(request, "mail/_message_body.html", {"body_html": body_html})


@mail_login_required
def image_proxy(request: HttpRequest) -> HttpResponse:
    """Stream one remote image, guarding against SSRF and oversized responses."""
    url = request.GET.get("u")
    if not isinstance(url, str) or not url:
        return HttpResponse(status=400)
    try:
        image = fetch_image(
            url,
            max_bytes=settings.MAIL_IMAGE_PROXY_MAX_BYTES,
            timeout=settings.MAIL_IMAGE_PROXY_TIMEOUT_SECONDS,
        )
    except ImageProxyError:
        return HttpResponse(status=404)
    response = HttpResponse(image.content, content_type=image.content_type)
    response["Cache-Control"] = "private, max-age=3600"
    return response


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
