"""URL routes for the mail folder and message list."""

from django.urls import path

from apps.mail.views import image_proxy, mailbox, message_remote_images, message_view

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
    path("message/<path:folder_name>/<int:uid>/", message_view, name="message"),
]
