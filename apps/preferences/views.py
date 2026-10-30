"""Preferences page and HTMX form handling."""

from __future__ import annotations

import json
from typing import Any, cast

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.vary import vary_on_headers

from apps.accounts.decorators import login_redirect, mail_login_required
from apps.accounts.exceptions import MailSessionError, PasswordChangeError, PasswordValidationError
from apps.accounts.services.password import change_account_password, is_password_change_configured
from apps.accounts.services.session import load_mail_account
from apps.mail.services.sieve_generator import VacationRule
from apps.mail.services.sieve_storage import (
    load_sieve_rules,
    load_vacation_rule,
    save_blocked_senders_to_sieve,
)
from apps.mail.views import get_account_folder_choices
from apps.preferences.forms import (
    AccountSignatureForm,
    BlockedSenderForm,
    ChangePasswordForm,
    MailPreferenceForm,
    TrustedSenderForm,
)
from apps.preferences.models import AccountSignature, BlockedSenderAction, MailPreference
from apps.preferences.services import (
    add_blocked_sender,
    add_trusted_sender,
    apply_mail_preference,
    delete_blocked_sender,
    delete_trusted_sender,
    get_account_signatures,
    get_blocked_senders,
    get_mail_preference,
    get_trusted_senders,
    sync_default_signature_to_session,
)


@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "POST"])
@mail_login_required
def index(request: HttpRequest) -> HttpResponse:
    """Render and save the account's presentation preferences."""
    try:
        preference = get_mail_preference(request)
    except MailSessionError:
        return login_redirect(request)

    if request.method == "POST":
        previous_language = preference.language
        form = MailPreferenceForm(request.POST, instance=preference)
        if form.is_valid():
            preference = form.save()
            apply_mail_preference(request, preference)
            if _is_htmx(request):
                response = _render(
                    request,
                    form,
                    preference,
                    htmx=True,
                    status=200,
                    saved=True,
                )
                response["HX-Trigger"] = json.dumps(
                    {
                        "mail:preference-changed": {
                            "theme": preference.theme,
                            "density": preference.density,
                            "notifications_enabled": preference.notifications_enabled,
                            "notification_sound_enabled": preference.notification_sound_enabled,
                        }
                    }
                )
                if preference.language != previous_language:
                    response["HX-Refresh"] = "true"
                return response
            messages.success(request, _("Preferences saved."))
            return redirect("preferences:index")

        return _render(
            request,
            form,
            preference,
            htmx=_is_htmx(request),
            status=200 if _is_htmx(request) else 422,
        )

    form = MailPreferenceForm(instance=preference)
    return _render(request, form, preference, htmx=_is_htmx(request), status=200)


def _render(
    request: HttpRequest,
    form: MailPreferenceForm,
    preference: MailPreference,
    *,
    htmx: bool,
    status: int,
    saved: bool = False,
) -> HttpResponse:
    incoming_rules = []
    outgoing_rules = []
    is_synced = False
    folder_choices = []
    vacation_rule = VacationRule()
    vacation_synced = False
    signatures = []
    trusted_senders = []
    blocked_senders = []
    if not htmx:
        account = getattr(request, "mail_account", None) or load_mail_account(request)
        if account:
            incoming_rules, outgoing_rules, is_synced = load_sieve_rules(request, account)
            vacation_rule, vacation_synced = load_vacation_rule(request, account)
            folder_choices = get_account_folder_choices(request)
            signatures = get_account_signatures(
                account.account_key,
                email=account.email,
                seed_from_pref=preference.signature_html,
            )
            trusted_senders = get_trusted_senders(account.account_key)
            blocked_senders = get_blocked_senders(account.account_key)
    active_tab = request.GET.get("tab", "incoming")
    if active_tab not in {"incoming", "outgoing"}:
        active_tab = "incoming"
    current_rules = incoming_rules if active_tab == "incoming" else outgoing_rules

    senders_tab = "trusted"
    if request.GET.get("section") == "senders":
        senders_tab = request.GET.get("tab", "trusted")

    context = {
        "form": form,
        "password_form": ChangePasswordForm(email=preference.email),
        "change_password_enabled": getattr(settings, "MAIL_CHANGE_PASSWORD_ENABLED", True),
        "password_backend_available": is_password_change_configured(),
        "email": preference.email,
        "display_name": preference.display_name,
        "account_label": preference.account_label,
        "saved": saved,
        "active_section": request.GET.get("section", "preferences"),
        "incoming_rules": incoming_rules,
        "outgoing_rules": outgoing_rules,
        "active_tab": active_tab,
        "active_rules": [r for r in current_rules if r.active],
        "available_rules": [r for r in current_rules if not r.active],
        "is_synced": is_synced,
        "vacation_rule": vacation_rule,
        "vacation_synced": vacation_synced,
        "folder_choices": folder_choices,
        "signatures": signatures,
        "trusted_senders": trusted_senders,
        "blocked_senders": blocked_senders,
        "trusted_sender_form": TrustedSenderForm(),
        "blocked_sender_form": BlockedSenderForm(),
        "senders_tab": senders_tab,
    }
    template = "preferences/_settings_form.html" if htmx else "preferences/index.html"
    return render(request, template, context, status=status)


def _is_htmx(request: HttpRequest) -> bool:
    return request.META.get("HTTP_HX_REQUEST") == "true"


@never_cache
@require_POST
@mail_login_required
def password_change_view(request: HttpRequest) -> HttpResponse:
    """Validate and update the account's password."""
    try:
        preference = get_mail_preference(request)
    except MailSessionError:
        return login_redirect(request)

    form = ChangePasswordForm(request.POST, email=preference.email)
    saved = False

    if form.is_valid():
        try:
            change_account_password(
                request,
                form.cleaned_data["current_password"],
                form.cleaned_data["new_password"],
            )
            saved = True
            form = ChangePasswordForm(email=preference.email)
        except (PasswordValidationError, PasswordChangeError) as exc:
            form.add_error(None, str(exc))

    context = {
        "form": MailPreferenceForm(instance=preference),
        "password_form": form,
        "password_saved": saved,
        "change_password_enabled": getattr(settings, "MAIL_CHANGE_PASSWORD_ENABLED", True),
        "password_backend_available": is_password_change_configured(),
        "email": preference.email,
        "display_name": preference.display_name,
        "account_label": preference.account_label,
        "active_section": "password",
    }
    status = 200 if (saved or _is_htmx(request)) else 422
    template = "preferences/_password_form.html" if _is_htmx(request) else "preferences/index.html"
    return render(request, template, context, status=status)


@never_cache
@require_GET
@mail_login_required
def signatures_panel(request: HttpRequest) -> HttpResponse:
    """Render the signatures management panel partial."""
    account = getattr(request, "mail_account", None) or load_mail_account(request)
    if not account:
        return login_redirect(request)
    pref = get_mail_preference(request)
    signatures = get_account_signatures(
        account.account_key,
        email=account.email,
        seed_from_pref=pref.signature_html,
    )
    context = {"signatures": signatures}
    return render(request, "preferences/_signatures_panel.html", context)


@never_cache
@require_GET
@mail_login_required
def signature_modal(request: HttpRequest) -> HttpResponse:
    """Render the create or edit signature modal dialog."""
    account = getattr(request, "mail_account", None) or load_mail_account(request)
    if not account:
        return login_redirect(request)
    sig_id = request.GET.get("sig_id")
    signature = None
    if sig_id:
        signature = (
            cast(Any, AccountSignature)
            .objects.filter(
                account_key=account.account_key,
                pk=sig_id,
            )
            .first()
        )

    form = AccountSignatureForm(instance=signature)
    context = {
        "form": form,
        "signature": signature,
        "is_edit": signature is not None,
    }
    return render(request, "preferences/_signature_modal.html", context)


@never_cache
@require_POST
@mail_login_required
def signature_save(request: HttpRequest) -> HttpResponse:
    """Save a created or edited signature."""
    account = getattr(request, "mail_account", None) or load_mail_account(request)
    if not account:
        return login_redirect(request)
    sig_id = request.POST.get("sig_id")
    instance = None
    if sig_id:
        instance = (
            cast(Any, AccountSignature)
            .objects.filter(
                account_key=account.account_key,
                pk=sig_id,
            )
            .first()
        )

    form = AccountSignatureForm(request.POST, instance=instance)
    if not form.is_valid():
        return render(
            request,
            "preferences/_signature_modal.html",
            {"form": form, "signature": instance, "is_edit": instance is not None},
            status=422 if not _is_htmx(request) else 200,
        )

    sig = form.save(commit=False)
    sig.account_key = account.account_key
    sig.email = account.email
    existing_count = (
        cast(Any, AccountSignature)
        .objects.filter(
            account_key=account.account_key,
        )
        .exclude(pk=sig.pk or 0)
        .count()
    )
    if existing_count == 0:
        sig.is_default = True
    sig.save()
    sync_default_signature_to_session(request)

    signatures = get_account_signatures(account.account_key)
    context = {
        "signatures": signatures,
        "status_message": _("Signature saved successfully."),
    }
    response = render(request, "preferences/_signatures_panel.html", context)
    response["HX-Trigger"] = json.dumps({"mail:signature-saved": True})
    return response


@never_cache
@require_POST
@mail_login_required
def signature_set_default(request: HttpRequest, sig_id: int) -> HttpResponse:
    """Mark a signature as the default for outgoing messages."""
    account = getattr(request, "mail_account", None) or load_mail_account(request)
    if not account:
        return login_redirect(request)
    sig = (
        cast(Any, AccountSignature)
        .objects.filter(
            account_key=account.account_key,
            pk=sig_id,
        )
        .first()
    )
    if sig:
        sig.is_default = True
        sig.is_active = True
        sig.save()
        sync_default_signature_to_session(request)

    signatures = get_account_signatures(account.account_key)
    context = {
        "signatures": signatures,
        "status_message": _("Default signature updated."),
    }
    return render(request, "preferences/_signatures_panel.html", context)


@never_cache
@require_POST
@mail_login_required
def signature_toggle_active(request: HttpRequest, sig_id: int) -> HttpResponse:
    """Toggle the active status of a signature."""
    account = getattr(request, "mail_account", None) or load_mail_account(request)
    if not account:
        return login_redirect(request)
    sig = (
        cast(Any, AccountSignature)
        .objects.filter(
            account_key=account.account_key,
            pk=sig_id,
        )
        .first()
    )
    if sig:
        sig.is_active = not sig.is_active
        if not sig.is_active and sig.is_default:
            sig.is_default = False
        sig.save()
        sync_default_signature_to_session(request)

    signatures = get_account_signatures(account.account_key)
    context = {"signatures": signatures}
    return render(request, "preferences/_signatures_panel.html", context)


@never_cache
@require_POST
@mail_login_required
def signature_delete(request: HttpRequest, sig_id: int) -> HttpResponse:
    """Delete a signature."""
    account = getattr(request, "mail_account", None) or load_mail_account(request)
    if not account:
        return login_redirect(request)
    cast(Any, AccountSignature).objects.filter(
        account_key=account.account_key,
        pk=sig_id,
    ).delete()
    sync_default_signature_to_session(request)

    signatures = get_account_signatures(account.account_key)
    context = {
        "signatures": signatures,
        "status_message": _("Signature deleted."),
    }
    return render(request, "preferences/_signatures_panel.html", context)


def _render_senders_panel(
    request: HttpRequest,
    account: Any,
    active_tab: str = "trusted",
    status_message: str = "",
) -> HttpResponse:
    trusted_senders = get_trusted_senders(account.account_key)
    blocked_senders = get_blocked_senders(account.account_key)
    context = {
        "trusted_senders": trusted_senders,
        "blocked_senders": blocked_senders,
        "trusted_sender_form": TrustedSenderForm(),
        "blocked_sender_form": BlockedSenderForm(),
        "senders_tab": active_tab,
        "status_message": status_message,
    }
    return render(request, "preferences/_senders_settings.html", context)


@never_cache
@require_http_methods(["GET"])
@mail_login_required
def senders_panel(request: HttpRequest) -> HttpResponse:
    """Render the senders management panel (trusted allowlist and blocked denylist)."""
    account = getattr(request, "mail_account", None) or load_mail_account(request)
    if not account:
        return login_redirect(request)
    tab = request.GET.get("tab", "trusted")
    if tab not in {"trusted", "blocked"}:
        tab = "trusted"
    return _render_senders_panel(request, account, active_tab=tab)


@never_cache
@require_POST
@mail_login_required
def trusted_sender_add_view(request: HttpRequest) -> HttpResponse:
    """Add a trusted sender or domain pattern."""
    account = getattr(request, "mail_account", None) or load_mail_account(request)
    if not account:
        return login_redirect(request)

    form = TrustedSenderForm(request.POST)
    msg = ""
    if form.is_valid():
        add_trusted_sender(
            account_key=account.account_key,
            email=account.email,
            pattern=form.cleaned_data["pattern"],
            description=form.cleaned_data.get("description", ""),
        )
        msg = _("Sender added to trusted allowlist.")

    return _render_senders_panel(request, account, active_tab="trusted", status_message=msg)


@never_cache
@require_POST
@mail_login_required
def trusted_sender_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove a pattern from the trusted allowlist."""
    account = getattr(request, "mail_account", None) or load_mail_account(request)
    if not account:
        return login_redirect(request)

    delete_trusted_sender(account.account_key, pk)
    msg = _("Sender removed from trusted allowlist.")
    return _render_senders_panel(request, account, active_tab="trusted", status_message=msg)


@never_cache
@require_POST
@mail_login_required
def blocked_sender_add_view(request: HttpRequest) -> HttpResponse:
    """Add a blocked sender or domain pattern and sync Sieve rule."""
    account = getattr(request, "mail_account", None) or load_mail_account(request)
    if not account:
        return login_redirect(request)

    form = BlockedSenderForm(request.POST)
    msg = ""
    if form.is_valid():
        add_blocked_sender(
            account_key=account.account_key,
            email=account.email,
            pattern=form.cleaned_data["pattern"],
            action=form.cleaned_data.get("action", BlockedSenderAction.TRASH),
            description=form.cleaned_data.get("description", ""),
        )
        save_blocked_senders_to_sieve(request, account)
        msg = _("Sender blocked and filter updated.")

    return _render_senders_panel(request, account, active_tab="blocked", status_message=msg)


@never_cache
@require_POST
@mail_login_required
def blocked_sender_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove a pattern from the blocked denylist and sync Sieve rule."""
    account = getattr(request, "mail_account", None) or load_mail_account(request)
    if not account:
        return login_redirect(request)

    delete_blocked_sender(account.account_key, pk)
    save_blocked_senders_to_sieve(request, account)
    msg = _("Sender unblocked and filter updated.")
    return _render_senders_panel(request, account, active_tab="blocked", status_message=msg)
