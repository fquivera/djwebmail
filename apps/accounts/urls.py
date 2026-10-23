"""URL routes for webmail authentication."""

from django.urls import path

from apps.accounts.views import MailLoginView, logout_view

app_name = "accounts"

urlpatterns = [
    path("login/", MailLoginView.as_view(), name="login"),
    path("logout/", logout_view, name="logout"),
]
