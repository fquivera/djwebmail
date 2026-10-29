"""Views for mail server administration and corporate identity."""

from __future__ import annotations

from typing import Any, cast

from django.contrib import messages
from django.db import DatabaseError, OperationalError, ProgrammingError
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import FormView, TemplateView, View

from apps.mailadmin.diagnostics import run_full_diagnostics
from apps.mailadmin.drivers import format_storage_bytes, get_account_driver
from apps.mailadmin.exceptions import MailAdminError
from apps.mailadmin.forms import (
    CorporateIdentityForm,
    MailboxCreateForm,
    MailboxEditForm,
)
from apps.mailadmin.models import CorporateIdentity
from apps.mailadmin.security import MailAdminRequiredMixin


class AdminIndexView(MailAdminRequiredMixin, TemplateView):
    """Main administrative control panel landing view."""

    template_name = "mailadmin/index.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["identity"] = CorporateIdentity.get_solo()
        context["page_title"] = _("Mail Server Administration")

        driver = get_account_driver()
        try:
            accounts = driver.list_accounts()
            context["accounts_count"] = len(accounts)
        except Exception:
            context["accounts_count"] = 0
        context["active_driver_name"] = driver.__class__.__name__
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

    def form_invalid(self, form: CorporateIdentityForm) -> HttpResponse:
        if self.request.headers.get("HX-Request") == "true":
            return render(
                self.request,
                "mailadmin/_branding_form.html",
                {
                    "form": form,
                    "identity": form.instance,
                    "saved": False,
                },
                status=422,
            )
        return cast(HttpResponse, super().form_invalid(form))

    def get_success_url(self) -> str:
        return reverse("mailadmin:branding")


class AccountListView(MailAdminRequiredMixin, TemplateView):
    """View to list, search, and monitor mail accounts and their quotas."""

    template_name = "mailadmin/accounts.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        status_filter = self.request.GET.get("status", "all").strip().lower()

        driver = get_account_driver()
        all_accounts = driver.list_accounts()

        if status_filter == "active":
            accounts = [a for a in all_accounts if a.is_active]
        elif status_filter == "inactive":
            accounts = [a for a in all_accounts if not a.is_active]
        else:
            accounts = all_accounts

        if query:
            q_lower = query.lower()
            accounts = [a for a in accounts if q_lower in a.email.lower()]

        total_bytes = sum(a.quota_bytes for a in all_accounts if a.quota_bytes is not None)

        context.update(
            {
                "accounts": accounts,
                "q": query,
                "status": status_filter,
                "total_count": len(all_accounts),
                "active_count": sum(1 for a in all_accounts if a.is_active),
                "inactive_count": sum(1 for a in all_accounts if not a.is_active),
                "total_quota_display": (
                    format_storage_bytes(total_bytes) if total_bytes else _("Unlimited")
                ),
                "page_title": _("Mail Accounts & Quotas"),
                "is_htmx": self.request.headers.get("HX-Request") == "true",
            }
        )
        return context

    def render_to_response(self, context: dict[str, Any], **response_kwargs: Any) -> HttpResponse:
        if self.request.headers.get("HX-Request") == "true":
            return render(self.request, "mailadmin/_accounts_list.html", context, **response_kwargs)
        return super().render_to_response(context, **response_kwargs)


class AccountCreateView(MailAdminRequiredMixin, FormView):
    """View to provision a new email account."""

    template_name = "mailadmin/account_form.html"
    form_class = MailboxCreateForm

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["is_create"] = True
        context["page_title"] = _("Create Mail Account")
        return context

    def form_valid(self, form: MailboxCreateForm) -> HttpResponse:
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]
        quota_bytes = form.cleaned_data.get("quota_bytes")
        is_active = form.cleaned_data.get("is_active", True)

        try:
            driver = get_account_driver()
            driver.create_account(
                email=email,
                password=password,
                quota_bytes=quota_bytes,
                is_active=is_active,
            )
            messages.success(
                self.request,
                _("Mail account '%(email)s' created successfully.") % {"email": email},
            )
        except MailAdminError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        if self.request.headers.get("HX-Request") == "true":
            response = HttpResponse(status=200)
            response["HX-Redirect"] = reverse("mailadmin:accounts")
            return response
        return redirect("mailadmin:accounts")

    def form_invalid(self, form: MailboxCreateForm) -> HttpResponse:
        context = self.get_context_data(form=form)
        return self.render_to_response(context, status=422)


class AccountEditView(MailAdminRequiredMixin, FormView):
    """View to update quota, status, or reset password of an existing mail account."""

    template_name = "mailadmin/account_form.html"
    form_class = MailboxEditForm

    def setup(self, request: Any, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        self.target_email = kwargs.get("email", "").strip().lower()
        driver = get_account_driver()
        self.account_data = driver.get_account(self.target_email)
        if not self.account_data:
            raise Http404(_("Mail account '%(email)s' not found.") % {"email": self.target_email})

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["email"] = self.target_email
        return kwargs

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        acc = self.account_data
        if not acc:
            return initial

        initial["is_active"] = acc.is_active
        if acc.quota_bytes is None:
            initial["quota_unit"] = "UNLIMITED"
            initial["quota_amount"] = None
        elif acc.quota_bytes >= 1024 * 1024 * 1024:
            initial["quota_unit"] = "GB"
            initial["quota_amount"] = acc.quota_bytes // (1024 * 1024 * 1024)
        else:
            initial["quota_unit"] = "MB"
            initial["quota_amount"] = acc.quota_bytes // (1024 * 1024)
        return initial

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["is_create"] = False
        context["account"] = self.account_data
        context["page_title"] = _("Edit Mail Account: %(email)s") % {"email": self.target_email}
        return context

    def form_valid(self, form: MailboxEditForm) -> HttpResponse:
        password = form.cleaned_data.get("password") or None
        quota_bytes = form.cleaned_data.get("quota_bytes")
        clear_quota = form.cleaned_data.get("clear_quota", False)
        is_active = form.cleaned_data.get("is_active")

        try:
            driver = get_account_driver()
            driver.update_account(
                email=self.target_email,
                password=password,
                quota_bytes=quota_bytes,
                is_active=is_active,
                clear_quota=clear_quota,
            )
            messages.success(
                self.request,
                _("Mail account '%(email)s' updated successfully.") % {"email": self.target_email},
            )
        except MailAdminError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        if self.request.headers.get("HX-Request") == "true":
            response = HttpResponse(status=200)
            response["HX-Redirect"] = reverse("mailadmin:accounts")
            return response
        return redirect("mailadmin:accounts")

    def form_invalid(self, form: MailboxEditForm) -> HttpResponse:
        context = self.get_context_data(form=form)
        return self.render_to_response(context, status=422)


class AccountToggleStatusView(MailAdminRequiredMixin, View):
    """View to quickly suspend or reactivate a mailbox."""

    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        email = kwargs.get("email", "").strip().lower()
        driver = get_account_driver()
        account = driver.get_account(email)
        if not account:
            raise Http404(_("Mail account '%(email)s' not found.") % {"email": email})

        new_status = not account.is_active
        try:
            driver.update_account(email=email, is_active=new_status)
            status_text = _("activated") if new_status else _("suspended")
            messages.success(
                request,
                _("Mail account '%(email)s' has been %(status)s.")
                % {"email": email, "status": status_text},
            )
        except MailAdminError as exc:
            messages.error(request, str(exc))

        if request.headers.get("HX-Request") == "true":
            response = HttpResponse(status=200)
            response["HX-Redirect"] = reverse("mailadmin:accounts")
            return response
        return redirect("mailadmin:accounts")


class AccountDeleteView(MailAdminRequiredMixin, View):
    """View to delete a mail account with confirmation."""

    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        email = kwargs.get("email", "").strip().lower()
        driver = get_account_driver()
        try:
            deleted = driver.delete_account(email)
            if deleted:
                messages.success(
                    request,
                    _("Mail account '%(email)s' deleted successfully.") % {"email": email},
                )
            else:
                messages.warning(
                    request,
                    _("Mail account '%(email)s' was not found.") % {"email": email},
                )
        except MailAdminError as exc:
            messages.error(request, str(exc))

        if request.headers.get("HX-Request") == "true":
            response = HttpResponse(status=200)
            response["HX-Redirect"] = reverse("mailadmin:accounts")
            return response
        return redirect("mailadmin:accounts")


class DiagnosticsView(MailAdminRequiredMixin, TemplateView):
    """View to probe and display service latency, server status, and diagnostics."""

    template_name = "mailadmin/diagnostics.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        report = run_full_diagnostics()
        context.update(report)
        context["page_title"] = _("Diagnostics & Service Health")
        return context

    def render_to_response(self, context: dict[str, Any], **response_kwargs: Any) -> HttpResponse:
        if self.request.headers.get("HX-Request") == "true":
            return render(
                self.request,
                "mailadmin/_diagnostics_content.html",
                context,
                **response_kwargs,
            )
        return super().render_to_response(context, **response_kwargs)
