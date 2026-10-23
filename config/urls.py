"""Root URL configuration."""

from django.contrib import admin
from django.urls import include, path

from common import views

urlpatterns = [
    path("", views.home, name="home"),
    path("health/", views.health, name="health"),
    path("", include("apps.accounts.urls")),
    path("admin/", admin.site.urls),
]
