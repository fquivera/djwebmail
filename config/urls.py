"""Root URL configuration."""

from django.contrib import admin
from django.urls import include, path

from common import views

urlpatterns = [
    path("", views.home, name="home"),
    path("health/", views.health, name="health"),
    path("", include("apps.accounts.urls")),
    path("mail/", include("apps.mail.urls")),
    path("compose/", include("apps.compose.urls")),
    path("settings/", include("apps.preferences.urls")),
    path("admin/", admin.site.urls),
]
