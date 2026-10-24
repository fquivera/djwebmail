"""URL routes for the mail folder and message list."""

from django.urls import path

from apps.mail.views import (
    attachment_view,
    image_proxy,
    inline_view,
    mailbox,
    message_flags,
    message_remote_images,
    message_view,
)

app_name = "mail"

urlpatterns = [
    path("", mailbox, name="index"),
    path("folder/<path:folder_name>/", mailbox, name="folder"),
    path("image-proxy/", image_proxy, name="image_proxy"),
    path(
        "message/<path:folder_name>/<int:uid>/remote-images/",
        message_remote_images,
        name="message_remote_images",
    ),
    path(
        "message/<path:folder_name>/<int:uid>/flags/",
        message_flags,
        name="message_flags",
    ),
    path(
        "message/<path:folder_name>/<int:uid>/attachment/<part>/",
        attachment_view,
        name="attachment",
    ),
    path(
        "message/<path:folder_name>/<int:uid>/inline/<part>/",
        inline_view,
        name="inline_image",
    ),
    path("message/<path:folder_name>/<int:uid>/", message_view, name="message"),
]
