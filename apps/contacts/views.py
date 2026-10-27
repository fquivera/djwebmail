"""Views for the RFC 7095 jCard contacts module."""

from __future__ import annotations

import json
from email.utils import parseaddr
from typing import Any, cast

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.vary import vary_on_headers

from apps.accounts.decorators import login_redirect, mail_login_required
from apps.contacts.constants import JCARD_MIME_TYPE, MAX_JCARD_IMPORT_BYTES
from apps.contacts.forms import ContactForm
from apps.contacts.jcard import decode_mime_text
from apps.contacts.models import Contact
from apps.contacts.selectors import get_contact, list_contacts
from apps.contacts.services import (
    delete_contact_for_account,
    export_jcard_for_account,
    import_jcard_for_account,
    save_contact_for_account,
)


@never_cache
@vary_on_headers("HX-Request")
@require_GET
@mail_login_required
def index(request: HttpRequest) -> HttpResponse:
    """Render the contacts directory and the create/edit contact form."""
    account_key = _account_key(request)
    if not account_key:
        return login_redirect(request)

    query = _query_text(request, "q").strip()
    contacts = list_contacts(account_key, query=query)

    if _is_htmx(request) and request.META.get("HTTP_HX_TARGET") == "contact-list-results":
        return render(
            request,
            "contacts/_contact_list.html",
            {"contacts": contacts, "query": query},
        )

    editing_contact = _resolve_editing_contact(request, account_key)
    form = _build_initial_form(request, account_key, editing_contact)
    return render(
        request,
        "contacts/index.html",
        {
            "contacts": contacts,
            "query": query,
            "form": form,
            "editing_contact": editing_contact,
        },
    )


@never_cache
@require_POST
@mail_login_required
def save(request: HttpRequest, contact_id: int | None = None) -> HttpResponse:
    """Create or update a contact and synchronize its RFC 7095 jCard payload."""
    account_key = _account_key(request)
    if not account_key:
        return login_redirect(request)

    instance: Contact | None = None
    if contact_id is not None:
        instance = get_contact(account_key, contact_id)
        if instance is None:
            raise Http404

    form = ContactForm(request.POST, instance=instance, account_key=account_key)
    if form.is_valid():
        contact = cast(Contact, form.save(commit=False))
        save_contact_for_account(account_key, contact)
        messages.success(request, _("Contact saved."))
        return redirect("contacts:index")

    return render(
        request,
        "contacts/index.html",
        {
            "contacts": list_contacts(account_key),
            "query": "",
            "form": form,
            "editing_contact": instance,
        },
        status=422,
    )


@never_cache
@require_POST
@mail_login_required
def delete(request: HttpRequest, contact_id: int) -> HttpResponse:
    """Delete a contact belonging to the current account."""
    account_key = _account_key(request)
    if not account_key:
        return login_redirect(request)

    if delete_contact_for_account(account_key, contact_id):
        messages.success(request, _("Contact deleted."))
    return redirect("contacts:index")


@never_cache
@require_GET
@mail_login_required
def export_jcard(request: HttpRequest) -> HttpResponse:
    """Export the account's contacts as a downloadable RFC 7095 jCard JSON file."""
    account_key = _account_key(request)
    if not account_key:
        return login_redirect(request)

    payload = export_jcard_for_account(account_key)
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    response = HttpResponse(
        body,
        content_type=f"{JCARD_MIME_TYPE}; charset=utf-8",
    )
    response["Content-Disposition"] = 'attachment; filename="contacts.jcard.json"'
    return response


@never_cache
@require_POST
@mail_login_required
def import_jcard(request: HttpRequest) -> HttpResponse:
    """Import a single RFC 7095 jCard or a JSON array of jCards."""
    account_key = _account_key(request)
    if not account_key:
        return login_redirect(request)

    raw_json = _extract_jcard_input(request)
    if raw_json is None:
        return redirect("contacts:index")

    try:
        created_count, updated_count = import_jcard_for_account(account_key, raw_json)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect("contacts:index")

    messages.success(
        request,
        _("jCard contacts imported: %(created)d new, %(updated)d updated.")
        % {"created": created_count, "updated": updated_count},
    )
    return redirect("contacts:index")


def _extract_jcard_input(request: HttpRequest) -> str | None:
    uploaded = cast(Any, request.FILES).get("jcard_file")
    if uploaded is not None:
        if getattr(uploaded, "size", 0) > MAX_JCARD_IMPORT_BYTES:
            messages.error(
                request,
                _("The jCard file exceeds the maximum allowed size."),
            )
            return None
        try:
            return uploaded.read(MAX_JCARD_IMPORT_BYTES + 1).decode("utf-8")
        except UnicodeDecodeError:
            messages.error(request, _("The jCard file must be UTF-8 encoded JSON."))
            return None

    raw_text = _post_text(request, "raw_json").strip()
    if not raw_text:
        messages.error(request, _("Select a jCard JSON file or paste a jCard payload."))
        return None
    if len(raw_text.encode("utf-8")) > MAX_JCARD_IMPORT_BYTES:
        messages.error(request, _("The jCard file exceeds the maximum allowed size."))
        return None
    return raw_text


def _resolve_editing_contact(request: HttpRequest, account_key: str) -> Contact | None:
    edit_raw = _query_text(request, "edit").strip()
    if not edit_raw.isdigit():
        return None
    return get_contact(account_key, int(edit_raw))


def _build_initial_form(
    request: HttpRequest,
    account_key: str,
    editing_contact: Contact | None,
) -> ContactForm:
    if editing_contact is not None:
        return ContactForm(instance=editing_contact, account_key=account_key)

    sender = _query_text(request, "sender").strip()
    if sender:
        parsed_name, parsed_addr = parseaddr(decode_mime_text(sender))
        addr = parsed_addr.strip().lower()
        raw_name = decode_mime_text(parsed_name)
        name = raw_name or (addr.split("@", 1)[0] if "@" in addr else decode_mime_text(sender))
        return ContactForm(
            initial={"full_name": name, "primary_email": addr},
            account_key=account_key,
        )

    return ContactForm(account_key=account_key)


def _query_text(request: HttpRequest, name: str) -> str:
    value = request.GET.get(name)
    return value if isinstance(value, str) else ""


def _post_text(request: HttpRequest, name: str) -> str:
    value = request.POST.get(name)
    return value if isinstance(value, str) else ""


def _account_key(request: HttpRequest) -> str:
    account = getattr(request, "mail_account", None)
    return getattr(account, "account_key", "")


def _is_htmx(request: HttpRequest) -> bool:
    return request.META.get("HTTP_HX_REQUEST") == "true"
