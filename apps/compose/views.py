"""Compose, reply, and forward views backed by SMTP."""

from __future__ import annotations

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
    get_mail_imap_service,
    get_mail_smtp_service,
)
from apps.compose.forms import ComposeForm
from apps.compose.services import forward_initial, reply_initial, send_message
from apps.mail.constants import IMAP_INBOX
from apps.mail.services.message import MessageDetail, get_message


@never_cache
@mail_login_required
def compose_new(request: HttpRequest) -> HttpResponse:
    """Render an empty compose form."""
    return render(request, "compose/compose.html", {"form": ComposeForm()})


@never_cache
@mail_login_required
def compose_reply(request: HttpRequest, folder_name: str, uid: int) -> HttpResponse:
    """Render a compose form prefilled as a reply."""
    message = _fetch_message(request, folder_name, uid)
    if isinstance(message, HttpResponse):
        return message
    return render(
        request,
        "compose/compose.html",
        {"form": ComposeForm(initial=reply_initial(message))},
    )


@never_cache
@mail_login_required
def compose_forward(request: HttpRequest, folder_name: str, uid: int) -> HttpResponse:
    """Render a compose form prefilled as a forward."""
    message = _fetch_message(request, folder_name, uid)
    if isinstance(message, HttpResponse):
        return message
    return render(
        request,
        "compose/compose.html",
        {"form": ComposeForm(initial=forward_initial(message))},
    )


@never_cache
@require_POST
@mail_login_required
def compose_send(request: HttpRequest) -> HttpResponse:
    """Validate the form and deliver the message over SMTP."""
    form = ComposeForm(request.POST)
    if not form.is_valid():
        return _render_form(request, form, status=422)

    account = getattr(request, "mail_account", None)
    if account is None:
        return login_redirect(request)

    try:
        with get_mail_smtp_service(request) as smtp:
            send_message(
                smtp,
                sender=account.email,
                to=form.cleaned_data["to"],
                cc=form.cleaned_data["cc"],
                subject=form.cleaned_data["subject"],
                body=form.cleaned_data["body"],
            )
    except MailSessionError:
        return login_redirect(request)
    except SmtpAuthError:
        form.add_error(
            None,
            _("The mail server rejected the stored credentials. Sign in again."),
        )
        return _render_form(request, form, status=503)
    except SmtpConnectionError:
        form.add_error(None, _("The mail server is unavailable. Try again later."))
        return _render_form(request, form, status=503)
    except SmtpSendError:
        form.add_error(
            None,
            _("The message could not be sent. Check the recipients and try again."),
        )
        return _render_form(request, form, status=422)

    return redirect("mail:index")


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


def _render_form(request: HttpRequest, form: ComposeForm, *, status: int) -> HttpResponse:
    return render(request, "compose/compose.html", {"form": form}, status=status)


def _error_response(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "mail/error.html",
        {"error": _("Unable to load the message. Try again later.")},
        status=503,
    )
