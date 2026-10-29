"""Preferences page and HTMX form handling."""

from __future__ import annotations

import json

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.vary import vary_on_headers

from apps.accounts.decorators import login_redirect, mail_login_required
from apps.accounts.exceptions import MailSessionError, PasswordChangeError, PasswordValidationError
from apps.accounts.services.password import change_account_password, is_password_change_configured
from apps.preferences.forms import ChangePasswordForm, MailPreferenceForm
from apps.preferences.models import MailPreference
from apps.preferences.services import apply_mail_preference, get_mail_preference


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
