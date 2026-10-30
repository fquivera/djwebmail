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
    AliasCreateForm,
    AliasEditForm,
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

        try:
            aliases = driver.list_aliases()
            context["aliases_count"] = len(aliases)
        except Exception:
            context["aliases_count"] = 0
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


class AliasListView(MailAdminRequiredMixin, TemplateView):
    """View to list, search, and filter virtual aliases and distribution lists."""

    template_name = "mailadmin/aliases.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get("q", "").strip()
        status_filter = self.request.GET.get("status", "all").strip().lower()
        type_filter = self.request.GET.get("type", "all").strip().lower()

        driver = get_account_driver()
        is_active_arg: bool | None = None
        if status_filter == "active":
            is_active_arg = True
        elif status_filter == "inactive":
            is_active_arg = False

        try:
            all_aliases = driver.list_aliases(search=search_query, is_active=is_active_arg)
        except MailAdminError as exc:
            messages.error(self.request, str(exc))
            all_aliases = []

        # Filter by type (alias = single destination, list = multi destination)
        if type_filter == "alias":
            aliases = [a for a in all_aliases if not a.is_distribution_list]
        elif type_filter == "list":
            aliases = [a for a in all_aliases if a.is_distribution_list]
        else:
            aliases = all_aliases

        # Overall summary stats
        try:
            unfiltered = driver.list_aliases()
            total_count = len(unfiltered)
            distribution_lists_count = sum(1 for a in unfiltered if a.is_distribution_list)
            virtual_aliases_count = total_count - distribution_lists_count
            active_count = sum(1 for a in unfiltered if a.is_active)
        except Exception:
            total_count = len(aliases)
            distribution_lists_count = sum(1 for a in aliases if a.is_distribution_list)
            virtual_aliases_count = total_count - distribution_lists_count
            active_count = sum(1 for a in aliases if a.is_active)

        context.update(
            {
                "aliases": aliases,
                "search_query": search_query,
                "status_filter": status_filter,
                "type_filter": type_filter,
                "total_count": total_count,
                "virtual_aliases_count": virtual_aliases_count,
                "distribution_lists_count": distribution_lists_count,
                "active_count": active_count,
                "active_driver_name": driver.__class__.__name__,
                "page_title": _("Aliases & Distribution Lists"),
            }
        )
        return context

    def render_to_response(self, context: dict[str, Any], **response_kwargs: Any) -> HttpResponse:
        if self.request.headers.get("HX-Request") == "true":
            return render(self.request, "mailadmin/_aliases_list.html", context, **response_kwargs)
        return super().render_to_response(context, **response_kwargs)


class AliasCreateView(MailAdminRequiredMixin, FormView):
    """View to provision a new virtual alias or distribution list."""

    template_name = "mailadmin/alias_form.html"
    form_class = AliasCreateForm

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["is_create"] = True
        context["page_title"] = _("Create Alias or Distribution List")
        return context

    def form_valid(self, form: AliasCreateForm) -> HttpResponse:
        source = form.cleaned_data["source"]
        name = form.cleaned_data.get("name", "")
        destinations = form.cleaned_data["destinations"]
        is_active = form.cleaned_data.get("is_active", True)

        try:
            driver = get_account_driver()
            driver.create_alias(
                source=source,
                destinations=destinations,
                name=name,
                is_active=is_active,
            )
            messages.success(
                self.request,
                _("Alias '%(source)s' created successfully.") % {"source": source},
            )
        except MailAdminError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        if self.request.headers.get("HX-Request") == "true":
            response = HttpResponse(status=200)
            response["HX-Redirect"] = reverse("mailadmin:aliases")
            return response
        return redirect("mailadmin:aliases")

    def form_invalid(self, form: AliasCreateForm) -> HttpResponse:
        context = self.get_context_data(form=form)
        return self.render_to_response(context, status=422)


class AliasEditView(MailAdminRequiredMixin, FormView):
    """View to edit an existing alias or distribution list."""

    template_name = "mailadmin/alias_form.html"
    form_class = AliasEditForm

    def setup(self, request: Any, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        self.target_source = kwargs.get("source", "").strip().lower()
        driver = get_account_driver()
        self.alias_data = driver.get_alias(self.target_source)
        if not self.alias_data:
            raise Http404(_("Alias '%(source)s' not found.") % {"source": self.target_source})

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["source"] = self.target_source
        return kwargs

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        alias = self.alias_data
        if not alias:
            return initial
        initial["name"] = alias.name
        initial["destinations"] = "\n".join(alias.destinations)
        initial["is_active"] = alias.is_active
        return initial

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["is_create"] = False
        context["alias"] = self.alias_data
        context["target_source"] = self.target_source
        context["page_title"] = _("Edit Alias: %(source)s") % {"source": self.target_source}
        return context

    def form_valid(self, form: AliasEditForm) -> HttpResponse:
        name = form.cleaned_data.get("name", "")
        destinations = form.cleaned_data["destinations"]
        is_active = form.cleaned_data.get("is_active", True)

        try:
            driver = get_account_driver()
            driver.update_alias(
                source=self.target_source,
                destinations=destinations,
                name=name,
                is_active=is_active,
            )
            messages.success(
                self.request,
                _("Alias '%(source)s' updated successfully.") % {"source": self.target_source},
            )
        except MailAdminError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        if self.request.headers.get("HX-Request") == "true":
            response = HttpResponse(status=200)
            response["HX-Redirect"] = reverse("mailadmin:aliases")
            return response
        return redirect("mailadmin:aliases")

    def form_invalid(self, form: AliasEditForm) -> HttpResponse:
        context = self.get_context_data(form=form)
        return self.render_to_response(context, status=422)


class AliasToggleStatusView(MailAdminRequiredMixin, View):
    """View to quickly suspend or activate an alias."""

    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        source = kwargs.get("source", "").strip().lower()
        driver = get_account_driver()
        try:
            current = driver.get_alias(source)
            if not current:
                raise Http404(_("Alias '%(source)s' not found.") % {"source": source})

            new_status = not current.is_active
            driver.update_alias(source=source, is_active=new_status)
            status_text = _("activated") if new_status else _("suspended")
            messages.success(
                request,
                _("Alias '%(source)s' has been %(status)s.")
                % {"source": source, "status": status_text},
            )
        except MailAdminError as exc:
            messages.error(request, str(exc))

        if request.headers.get("HX-Request") == "true":
            response = HttpResponse(status=200)
            response["HX-Redirect"] = reverse("mailadmin:aliases")
            return response
        return redirect("mailadmin:aliases")


class AliasDeleteView(MailAdminRequiredMixin, View):
    """View to delete an alias or distribution list."""

    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        source = kwargs.get("source", "").strip().lower()
        driver = get_account_driver()
        try:
            deleted = driver.delete_alias(source)
            if deleted:
                messages.success(
                    request,
                    _("Alias '%(source)s' deleted successfully.") % {"source": source},
                )
            else:
                messages.warning(
                    request,
                    _("Alias '%(source)s' was not found.") % {"source": source},
                )
        except MailAdminError as exc:
            messages.error(request, str(exc))

        if request.headers.get("HX-Request") == "true":
            response = HttpResponse(status=200)
            response["HX-Redirect"] = reverse("mailadmin:aliases")
            return response
        return redirect("mailadmin:aliases")
