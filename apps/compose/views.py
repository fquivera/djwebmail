"""Compose, reply, forward, attachment, and draft views."""

from __future__ import annotations

from contextlib import suppress
from typing import Any, cast

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.decorators import login_redirect, mail_login_required
from apps.accounts.exceptions import (
    ImapAuthError,
    MailError,
    MailSessionError,
    SmtpAuthError,
    SmtpConnectionError,
    SmtpSendError,
)
from apps.accounts.services.session import (
    end_mail_session,
    get_mail_account_label,
    get_mail_display_name,
    get_mail_imap_service,
    get_mail_signature,
    get_mail_smtp_service,
)
from apps.compose.attachments import (
    clear_attachments,
    list_attachments,
    load_attachments,
    remove_attachment,
    save_upload,
)
from apps.compose.drafts import clear_draft, load_draft, save_draft
from apps.compose.exceptions import (
    AttachmentLimitReachedError,
    AttachmentTooLargeError,
    EmptyAttachmentError,
)
from apps.compose.forms import ComposeForm
from apps.compose.services import (
    append_to_sent,
    apply_signature,
    format_sender_address,
    forward_initial,
    reply_all_initial,
    reply_initial,
    send_message,
)
from apps.mail.constants import IMAP_INBOX
from apps.mail.services.message import MessageDetail, get_message


@never_cache
@mail_login_required
def compose_new(request: HttpRequest) -> HttpResponse:
    """Render the compose form, restoring an autosaved draft when present."""
    session_key = _session_key(request)
    draft = load_draft(session_key)
    signature = get_mail_signature(request)
    if draft:
        initial: dict[str, str] | None = draft.as_initial()
    elif signature:
        initial = apply_signature({}, signature)
    else:
        initial = None
    return _render_compose(
        request,
        session_key,
        ComposeForm(initial=initial),
        draft_autosave=True,
    )


@never_cache
@mail_login_required
def compose_reply(request: HttpRequest, folder_name: str, uid: int) -> HttpResponse:
    """Render a compose form prefilled as a reply."""
    message = _fetch_message(request, folder_name, uid)
    if isinstance(message, HttpResponse):
        return message
    initial = apply_signature(reply_initial(message), get_mail_signature(request))
    return _render_compose(
        request,
        _session_key(request),
        ComposeForm(initial=initial),
    )


@never_cache
@mail_login_required
def compose_reply_all(request: HttpRequest, folder_name: str, uid: int) -> HttpResponse:
    """Render a compose form prefilled as a reply to all participants."""
    message = _fetch_message(request, folder_name, uid)
    if isinstance(message, HttpResponse):
        return message
    account = getattr(request, "mail_account", None)
    account_email = account.email if account is not None else ""
    initial = apply_signature(
        reply_all_initial(message, account_email),
        get_mail_signature(request),
    )
    return _render_compose(
        request,
        _session_key(request),
        ComposeForm(initial=initial),
    )


@never_cache
@mail_login_required
def compose_forward(request: HttpRequest, folder_name: str, uid: int) -> HttpResponse:
    """Render a compose form prefilled as a forward."""
    message = _fetch_message(request, folder_name, uid)
    if isinstance(message, HttpResponse):
        return message
    initial = apply_signature(forward_initial(message), get_mail_signature(request))
    return _render_compose(
        request,
        _session_key(request),
        ComposeForm(initial=initial),
    )


@never_cache
@require_POST
@mail_login_required
def compose_send(request: HttpRequest) -> HttpResponse:
    """Validate the form and deliver the message over SMTP."""
    session_key = _session_key(request)
    form = ComposeForm(request.POST)
    if not form.is_valid():
        return _render_compose(request, session_key, form, status=422)

    account = getattr(request, "mail_account", None)
    if account is None:
        return login_redirect(request)

    attachments = load_attachments(session_key, _attachment_ids(request))
    display_name = get_mail_display_name(request)
    try:
        with get_mail_smtp_service(request) as smtp:
            raw = send_message(
                smtp,
                sender=account.email,
                sender_name=display_name,
                to=form.cleaned_data["to"],
                cc=form.cleaned_data["cc"],
                bcc=form.cleaned_data.get("bcc", []),
                subject=form.cleaned_data["subject"],
                body=form.cleaned_data["body"],
                attachments=attachments,
            )
    except MailSessionError:
        return login_redirect(request)
    except SmtpAuthError:
        form.add_error(
            None,
            _("The mail server rejected the stored credentials. Sign in again."),
        )
        return _render_compose(request, session_key, form, status=503)
    except SmtpConnectionError:
        form.add_error(None, _("The mail server is unavailable. Try again later."))
        return _render_compose(request, session_key, form, status=503)
    except SmtpSendError:
        form.add_error(
            None,
            _("The message could not be sent. Check the recipients and try again."),
        )
        return _render_compose(request, session_key, form, status=422)

    with suppress(MailError):
        with get_mail_imap_service(request) as imap:
            append_to_sent(imap, raw)

    clear_draft(session_key)
    clear_attachments(session_key)
    return redirect("mail:index")


@never_cache
@require_POST
@mail_login_required
def compose_attachments(request: HttpRequest) -> HttpResponse:
    """Store uploaded files for this session and refresh the attachment list."""
    session_key = _session_key(request)
    uploads = cast(list[UploadedFile], request.FILES.getlist("attachments"))
    error = ""
    if not uploads:
        error = _("Choose at least one file to attach.")
    for upload in uploads:
        try:
            save_upload(session_key, upload)
        except EmptyAttachmentError:
            error = _("One of the files is empty.")
        except AttachmentTooLargeError:
            error = _("That file is too large to attach.")
        except AttachmentLimitReachedError:
            error = _("You reached the attachment limit.")
    return _render_attachment_list(request, session_key, error=error)


@never_cache
@require_POST
@mail_login_required
def compose_attachment_delete(request: HttpRequest, attachment_id: str) -> HttpResponse:
    """Remove one stored attachment from the compose form."""
    session_key = _session_key(request)
    remove_attachment(session_key, attachment_id)
    return _render_attachment_list(request, session_key)


@never_cache
@require_POST
@mail_login_required
def compose_draft(request: HttpRequest) -> HttpResponse:
    """Autosave the form text under the session scope."""
    session_key = _session_key(request)
    save_draft(
        session_key,
        to=_post_text(request, "to"),
        cc=_post_text(request, "cc"),
        bcc=_post_text(request, "bcc"),
        subject=_post_text(request, "subject"),
        body=_post_text(request, "body"),
    )
    return HttpResponse(status=204)


def _fetch_message(
    request: HttpRequest,
    folder_name: str,
    uid: int,
) -> MessageDetail | HttpResponse:
    """Fetch one message, returning the right response when it is unavailable."""
    folder = folder_name or IMAP_INBOX
    try:
        with get_mail_imap_service(request) as imap:
            return get_message(imap, folder, uid)
    except MailSessionError:
        return login_redirect(request)
    except ImapAuthError:
        end_mail_session(request)
        return login_redirect(request)
    except MailError:
        return _error_response(request)


def _render_compose(
    request: HttpRequest,
    session_key: str,
    form: ComposeForm,
    *,
    status: int = 200,
    attachment_error: str = "",
    draft_autosave: bool = False,
) -> HttpResponse:
    account = getattr(request, "mail_account", None)
    account_email = account.email if account is not None else ""
    display_name = get_mail_display_name(request)
    return render(
        request,
        "compose/compose.html",
        {
            "form": form,
            "attachments": list_attachments(session_key),
            "attachment_error": attachment_error,
            "max_attachment_bytes": settings.MAIL_MAX_ATTACHMENT_BYTES,
            "draft_autosave": draft_autosave,
            "sender_display": format_sender_address(account_email, display_name),
            "account_label": get_mail_account_label(request),
        },
        status=status,
    )


def _render_attachment_list(
    request: HttpRequest,
    session_key: str,
    *,
    error: str = "",
) -> HttpResponse:
    return render(
        request,
        "compose/_attachment_list.html",
        {
            "attachments": list_attachments(session_key),
            "attachment_error": error,
        },
    )


def _attachment_ids(request: HttpRequest) -> list[str]:
    values = cast(list[Any], request.POST.getlist("attachment_ids"))
    return [value for value in values if isinstance(value, str)]


def _post_text(request: HttpRequest, name: str) -> str:
    value = request.POST.get(name)
    return value if isinstance(value, str) else ""


def _session_key(request: HttpRequest) -> str:
    session = cast(Any, request).session
    if session.session_key is None:
        session.create()
    session_key = session.session_key
    if not session_key:
        raise MailSessionError("The mail session has no key")
    return session_key


def _error_response(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "mail/error.html",
        {"error": _("Unable to load the message. Try again later.")},
        status=503,
    )
