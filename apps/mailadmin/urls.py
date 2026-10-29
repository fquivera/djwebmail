"""URL routes for the mailadmin application."""

from __future__ import annotations

from django.urls import path

from apps.mailadmin import views

app_name = "mailadmin"

urlpatterns = [
    path("", views.AdminIndexView.as_view(), name="index"),
    path("branding/", views.CorporateIdentityView.as_view(), name="branding"),
]
