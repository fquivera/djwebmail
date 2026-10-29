"""URL routes for the mailadmin application."""

from __future__ import annotations

from django.urls import path

from apps.mailadmin import views

app_name = "mailadmin"

urlpatterns = [
    path("", views.AdminIndexView.as_view(), name="index"),
    path("branding/", views.CorporateIdentityView.as_view(), name="branding"),
    path("accounts/", views.AccountListView.as_view(), name="accounts"),
    path("accounts/new/", views.AccountCreateView.as_view(), name="account_create"),
    path("accounts/<str:email>/edit/", views.AccountEditView.as_view(), name="account_edit"),
    path(
        "accounts/<str:email>/toggle/",
        views.AccountToggleStatusView.as_view(),
        name="account_toggle",
    ),
    path("accounts/<str:email>/delete/", views.AccountDeleteView.as_view(), name="account_delete"),
    path("diagnostics/", views.DiagnosticsView.as_view(), name="diagnostics"),
]
