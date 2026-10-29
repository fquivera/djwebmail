"""Views for mail server administration and corporate identity."""

from __future__ import annotations

from typing import Any, cast

from django.contrib import messages
from django.db import DatabaseError, OperationalError, ProgrammingError
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import FormView, TemplateView

from apps.mailadmin.forms import CorporateIdentityForm
from apps.mailadmin.models import CorporateIdentity
from apps.mailadmin.security import MailAdminRequiredMixin


class AdminIndexView(MailAdminRequiredMixin, TemplateView):
    """Main administrative control panel landing view."""

    template_name = "mailadmin/index.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["identity"] = CorporateIdentity.get_solo()
        context["page_title"] = _("Mail Server Administration")
        return context


class CorporateIdentityView(MailAdminRequiredMixin, FormView):
    """View to configure corporate identity, logos, fiscal address, and contacts."""

    template_name = "mailadmin/branding.html"
    form_class = CorporateIdentityForm

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = CorporateIdentity.get_solo()
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["identity"] = CorporateIdentity.get_solo()
        context["page_title"] = _("Corporate Identity & Branding")
        return context

    def form_valid(self, form: CorporateIdentityForm) -> HttpResponse:
        try:
            form.save()
            messages.success(self.request, _("Corporate identity settings saved successfully."))
            saved = True
        except (DatabaseError, ProgrammingError, OperationalError):
            form.add_error(None, _("Database table is not available. Please run migrations."))
            saved = False

        if self.request.headers.get("HX-Request") == "true":
            response = render(
                self.request,
                "mailadmin/_branding_form.html",
                {
                    "form": form,
                    "identity": form.instance,
                    "saved": saved,
                },
                status=200 if saved else 422,
            )
            if saved:
                response["HX-Trigger"] = "brandingUpdated"
            return response

        if not saved:
            return self.form_invalid(form)

        return cast(HttpResponse, super().form_valid(form))

    def get_success_url(self) -> str:
        return reverse("mailadmin:branding")
