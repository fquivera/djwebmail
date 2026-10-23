"""IMAP-backed login and logout views."""

from __future__ import annotations

from typing import cast

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.generic import FormView

from apps.accounts.exceptions import (
    ImapAuthError,
    ImapConnectionError,
    MailConfigurationError,
    MailError,
    MailSessionError,
)
from apps.accounts.forms import LoginForm
from apps.accounts.services.session import (
    authenticate_mail_account,
    end_mail_session,
    start_mail_session,
)
from apps.accounts.services.throttle import LoginThrottle


@method_decorator(never_cache, name="dispatch")
class MailLoginView(FormView):
    """Authenticate against IMAP and create the server-side mail session."""

    template_name = "accounts/login.html"
    form_class = LoginForm

    def dispatch(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if getattr(request, "mail_account", None) is not None:
            return redirect(self.get_success_url())
        return cast(HttpResponse, super().dispatch(request, *args, **kwargs))

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        context["next"] = self.request.POST.get("next") or self.request.GET.get("next") or ""
        return context

    def form_valid(self, form: LoginForm) -> HttpResponse:
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]
        throttle = LoginThrottle()
        throttle_key = throttle.key(email, self.request.META.get("REMOTE_ADDR", ""))

        if throttle.is_blocked(throttle_key):
            return self._invalid(
                form,
                _("Too many failed attempts. Try again later."),
                status=429,
            )

        try:
            account = authenticate_mail_account(email, password)
        except ImapAuthError:
            throttle.record_failure(throttle_key)
            return self._invalid(form, _("Invalid email or password."))
        except ImapConnectionError:
            throttle.record_failure(throttle_key)
            return self._invalid(
                form,
                _("The mail server is unavailable. Try again later."),
                status=503,
            )
        except MailConfigurationError:
            return self._invalid(
                form,
                _("Mail sign-in is not configured. Contact the administrator."),
                status=503,
            )
        except MailError:
            throttle.record_failure(throttle_key)
            return self._invalid(form, _("Unable to sign in."))

        try:
            start_mail_session(self.request, account, password)
        except (MailConfigurationError, MailSessionError):
            return self._invalid(
                form,
                _("Mail sign-in is not configured. Contact the administrator."),
                status=503,
            )

        throttle.clear(throttle_key)
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return next_url
        return reverse("home")

    def _invalid(self, form: LoginForm, message: str, *, status: int = 200) -> HttpResponse:
        form.add_error(None, message)
        return self.render_to_response(self.get_context_data(form=form), status=status)


@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    """Delete the encrypted credential and invalidate the session."""
    end_mail_session(request)
    return redirect("accounts:login")
