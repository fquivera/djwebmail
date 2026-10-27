"""URL routes for the mail folder and message list."""

from django.urls import path

from apps.mail.views import (
    attachment_view,
    folder_create,
    image_proxy,
    inline_view,
    mailbox,
    message_delete,
    message_flags,
    message_move,
    message_remote_images,
    message_view,
    messages_batch,
    palette,
    search,
)

app_name = "mail"

urlpatterns = [
    path("", mailbox, name="index"),
    path("folders/create/", folder_create, name="folder_create"),
    path("folder/<path:folder_name>/batch/", messages_batch, name="messages_batch"),
    path("folder/<path:folder_name>/", mailbox, name="folder"),
    path("search/", search, name="search"),
    path("palette/", palette, name="palette"),
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
        "message/<path:folder_name>/<int:uid>/move/",
        message_move,
        name="message_move",
    ),
    path(
        "message/<path:folder_name>/<int:uid>/delete/",
        message_delete,
        name="message_delete",
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
