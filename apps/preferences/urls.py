"""URL routes for account preferences."""

from django.urls import path

from apps.preferences.views import index

app_name = "preferences"

urlpatterns = [
    path("", index, name="index"),
]
