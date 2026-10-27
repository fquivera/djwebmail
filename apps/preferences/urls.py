"""URL routes for account preferences."""

from django.urls import path

from apps.preferences.views import index, password_change_view

app_name = "preferences"

urlpatterns = [
    path("", index, name="index"),
    path("password/", password_change_view, name="password"),
]
