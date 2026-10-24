"""Folder tree and message list views."""

from __future__ import annotations

from urllib.parse import quote

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers

from apps.accounts.decorators import login_redirect, mail_login_required
from apps.accounts.exceptions import ImapAuthError, MailError, MailSessionError
from apps.accounts.services.session import end_mail_session, get_mail_imap_service
from apps.mail.constants import (
    IMAGE_PROXY_ALLOWED_CONTENT_TYPES,
    IMAP_INBOX,
    MESSAGE_FLAG_FLAGGED,
    MESSAGE_FLAG_SEEN,
)
from apps.mail.services.image_proxy import ImageProxyError, fetch_image
from apps.mail.services.mailbox import (
    list_folders,
    list_messages,
    move_message,
    set_message_flags,
)
from apps.mail.services.message import MessageDetail, get_message, get_part, rewrite_images


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
            folders = list_folders(imap)
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
        "message": message,
        "body_html": _render_body_html(message, folder, uid, allow_remote=False),
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
            message = get_message(imap, folder, uid)
    except MailSessionError:
        return login_redirect(request)
    except ImapAuthError:
        end_mail_session(request)
        return login_redirect(request)
    except MailError:
        return _error_response(request)

    body_html = _render_body_html(message, folder, uid, allow_remote=True)
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


@never_cache
@require_POST
@mail_login_required
def message_flags(request: HttpRequest, folder_name: str, uid: int) -> HttpResponse:
    """Apply a read/star flag change and refresh the row (and viewer)."""
    action = request.POST.get("action")
    if not isinstance(action, str):
        return HttpResponse(status=400)
    add, remove = _flag_action(action)
    if not add and not remove:
        return HttpResponse(status=400)

    folder = folder_name or IMAP_INBOX
    try:
        with get_mail_imap_service(request) as imap:
            summary = set_message_flags(imap, folder, uid, add=add, remove=remove)
            message = get_message(imap, folder, uid)
            folders = list_folders(imap)
    except MailSessionError:
        return login_redirect(request)
    except ImapAuthError:
        end_mail_session(request)
        return login_redirect(request)
    except MailError:
        return _error_response(request)

    if summary is None:
        return HttpResponse(status=404)

    if action in ("star", "unstar"):
        return render(
            request,
            "mail/_message_flags_response.html",
            {
                "folder_name": folder,
                "folders": folders,
                "message": message,
                "body_html": _render_body_html(message, folder, uid, allow_remote=False),
                "row": summary,
            },
        )
    return render(
        request,
        "mail/_message_row.html",
        {"message": summary, "folder_name": folder, "oob": True},
    )


@never_cache
@require_POST
@mail_login_required
def message_move(request: HttpRequest, folder_name: str, uid: int) -> HttpResponse:
    """Move one message to another folder and follow it there."""
    destination = request.POST.get("dest")
    if not isinstance(destination, str) or not destination:
        return HttpResponse(status=400)

    folder = folder_name or IMAP_INBOX
    try:
        with get_mail_imap_service(request) as imap:
            move_message(imap, folder, uid, destination)
    except MailSessionError:
        return login_redirect(request)
    except ImapAuthError:
        end_mail_session(request)
        return login_redirect(request)
    except MailError:
        return _error_response(request)

    target = reverse("mail:folder", kwargs={"folder_name": destination})
    if request.META.get("HTTP_HX_REQUEST") == "true":
        return HttpResponse(status=204, headers={"HX-Redirect": target})
    return redirect(target)


@never_cache
@mail_login_required
def attachment_view(
    request: HttpRequest,
    folder_name: str,
    uid: int,
    part: str,
) -> HttpResponse:
    """Stream one message part as a download."""
    return _stream_part(request, folder_name, uid, part, inline=False)


@never_cache
@mail_login_required
def inline_view(
    request: HttpRequest,
    folder_name: str,
    uid: int,
    part: str,
) -> HttpResponse:
    """Stream one message part as an inline image (cid: references)."""
    return _stream_part(request, folder_name, uid, part, inline=True)


def _render_body_html(
    message: MessageDetail,
    folder: str,
    uid: int,
    *,
    allow_remote: bool,
) -> str:
    def inline_url(part: str) -> str:
        return reverse(
            "mail:inline_image",
            kwargs={"folder_name": folder, "uid": uid, "part": part},
        )

    return rewrite_images(
        message.body_html,
        proxy_base=reverse("mail:image_proxy"),
        inline_url=inline_url,
        inline_cids=message.inline_cids,
        allow_remote=allow_remote,
    )


def _stream_part(
    request: HttpRequest,
    folder_name: str,
    uid: int,
    part: str,
    *,
    inline: bool,
) -> HttpResponse:
    folder = folder_name or IMAP_INBOX
    try:
        with get_mail_imap_service(request) as imap:
            result = get_part(imap, folder, uid, part)
    except MailSessionError:
        return login_redirect(request)
    except ImapAuthError:
        end_mail_session(request)
        return login_redirect(request)
    except MailError:
        return HttpResponse(status=404)

    if result is None:
        return HttpResponse(status=404)
    content, content_type, filename, disposition = result

    if inline and content_type not in IMAGE_PROXY_ALLOWED_CONTENT_TYPES:
        return HttpResponse(status=404)

    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = _content_disposition(
        "inline" if inline else disposition,
        filename,
    )
    response["Cache-Control"] = "private, max-age=3600"
    return response


def _content_disposition(disposition: str, filename: str) -> str:
    safe = _safe_filename(filename)
    ascii_name = safe.encode("ascii", "replace").decode("ascii")
    if ascii_name != safe:
        return f"{disposition}; filename*=UTF-8''{quote(safe)}"
    return f'{disposition}; filename="{ascii_name}"'


def _safe_filename(filename: str) -> str:
    for char in ("\r", "\n", '"', "\\"):
        filename = filename.replace(char, "")
    return filename.strip() or "attachment"


_FLAG_ACTIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "read": ((MESSAGE_FLAG_SEEN,), ()),
    "unread": ((), (MESSAGE_FLAG_SEEN,)),
    "star": ((MESSAGE_FLAG_FLAGGED,), ()),
    "unstar": ((), (MESSAGE_FLAG_FLAGGED,)),
}


def _flag_action(action: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return _FLAG_ACTIONS.get(action or "", ((), ()))


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
