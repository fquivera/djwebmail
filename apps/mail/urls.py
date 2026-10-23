"""URL routes for the mail folder and message list."""

from django.urls import path

from apps.mail.views import mailbox, message_view

app_name = "mail"

urlpatterns = [
    path("", mailbox, name="index"),
    path("folder/<path:folder_name>/", mailbox, name="folder"),
    path("message/<path:folder_name>/<int:uid>/", message_view, name="message"),
]
