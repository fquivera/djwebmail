"""Tests for mailadmin security and access control."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.views import View

from apps.accounts.constants import SESSION_EMAIL_KEY
from apps.mailadmin.security import (
    MailAdminRequiredMixin,
    is_mail_admin,
    mail_admin_required,
)


class DummyAdminView(MailAdminRequiredMixin, View):
    def get(self, request: Any) -> HttpResponse:
        return HttpResponse(b"OK")


@pytest.fixture
def factory() -> RequestFactory:
    return RequestFactory()


def test_is_mail_admin_staff_user(factory: RequestFactory) -> None:
    request = factory.get("/")
    user = MagicMock()
    user.is_authenticated = True
    user.is_staff = True
    user.is_superuser = False
    cast(Any, request).user = user

    assert is_mail_admin(request) is True


def test_is_mail_admin_superuser(factory: RequestFactory) -> None:
    request = factory.get("/")
    user = MagicMock()
    user.is_authenticated = True
    user.is_staff = False
    user.is_superuser = True
    cast(Any, request).user = user

    assert is_mail_admin(request) is True


@override_settings(MAIL_ADMIN_ACCOUNTS=["admin@example.com"])
def test_is_mail_admin_session_match(factory: RequestFactory) -> None:
    request = factory.get("/")
    cast(Any, request).user = MagicMock(is_authenticated=False)
    request.session = {SESSION_EMAIL_KEY: "admin@example.com"}  # type: ignore[assignment]

    assert is_mail_admin(request) is True


@override_settings(MAIL_ADMIN_ACCOUNTS=["admin@example.com"])
def test_is_mail_admin_session_case_insensitive(factory: RequestFactory) -> None:
    request = factory.get("/")
    cast(Any, request).user = MagicMock(is_authenticated=False)
    request.session = {SESSION_EMAIL_KEY: "ADMIN@EXAMPLE.COM"}  # type: ignore[assignment]

    assert is_mail_admin(request) is True


@override_settings(MAIL_ADMIN_ACCOUNTS=["admin@example.com"])
def test_is_mail_admin_session_unauthorized(factory: RequestFactory) -> None:
    request = factory.get("/")
    cast(Any, request).user = MagicMock(is_authenticated=False)
    request.session = {SESSION_EMAIL_KEY: "user@example.com"}  # type: ignore[assignment]

    assert is_mail_admin(request) is False


def test_is_mail_admin_anonymous(factory: RequestFactory) -> None:
    request = factory.get("/")
    cast(Any, request).user = MagicMock(is_authenticated=False)
    request.session = {}  # type: ignore[assignment]

    assert is_mail_admin(request) is False


def test_mixin_redirects_anonymous_user(factory: RequestFactory) -> None:
    request = factory.get("/mailadmin/")
    cast(Any, request).user = MagicMock(is_authenticated=False)
    request.session = {}  # type: ignore[assignment]

    view = DummyAdminView.as_view()
    response = view(request)
    assert response.status_code == 302
    assert "/login/" in response["Location"]


@override_settings(MAIL_ADMIN_ACCOUNTS=["admin@example.com"])
def test_mixin_forbids_non_admin_session_user(factory: RequestFactory) -> None:
    request = factory.get("/mailadmin/")
    cast(Any, request).user = MagicMock(is_authenticated=False)
    request.session = {SESSION_EMAIL_KEY: "user@example.com"}  # type: ignore[assignment]

    view = DummyAdminView.as_view()
    with pytest.raises(PermissionDenied):
        view(request)


@override_settings(MAIL_ADMIN_ACCOUNTS=["admin@example.com"])
def test_decorator_allows_admin(factory: RequestFactory) -> None:
    @mail_admin_required
    def protected_view(request: Any) -> HttpResponse:
        return HttpResponse(b"Secret")

    request = factory.get("/mailadmin/")
    cast(Any, request).user = MagicMock(is_authenticated=False)
    request.session = {SESSION_EMAIL_KEY: "admin@example.com"}  # type: ignore[assignment]

    response = protected_view(request)
    assert response.status_code == 200
    assert response.content == b"Secret"
