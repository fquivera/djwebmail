"""URL routes for the mail folder and message list."""

from django.urls import path

from apps.mail.views import mailbox

app_name = "mail"

urlpatterns = [
    path("", mailbox, name="index"),
    path("folder/<path:folder_name>/", mailbox, name="folder"),
]
