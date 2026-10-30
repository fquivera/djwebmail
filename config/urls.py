"""Root URL configuration."""

import re

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from common import views

urlpatterns = [
    path("", views.home, name="home"),
    path("health/", views.health, name="health"),
    path("", include("apps.accounts.urls")),
    path("mail/", include("apps.mail.urls")),
    path("compose/", include("apps.compose.urls")),
    path("contacts/", include("apps.contacts.urls")),
    path("settings/", include("apps.preferences.urls")),
    path("mailadmin/", include("apps.mailadmin.urls")),
    path("admin/", admin.site.urls),
    re_path(
        rf"^{re.escape(settings.MEDIA_URL.lstrip('/'))}(?P<path>.*)$",
        serve,
        {"document_root": settings.MEDIA_ROOT},
    ),
]

if settings.DEBUG:
    try:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass
