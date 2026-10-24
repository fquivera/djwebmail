"""Preferences page and HTMX form handling."""

from __future__ import annotations

import json

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.views.decorators.vary import vary_on_headers

from apps.accounts.decorators import login_redirect, mail_login_required
from apps.accounts.exceptions import MailSessionError
from apps.preferences.forms import MailPreferenceForm
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
        "email": preference.email,
        "saved": saved,
    }
    template = "preferences/_settings_form.html" if htmx else "preferences/index.html"
    return render(request, template, context, status=status)


def _is_htmx(request: HttpRequest) -> bool:
    return request.META.get("HTTP_HX_REQUEST") == "true"
