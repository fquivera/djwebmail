"""URL routes for composing and sending mail."""

from django.urls import path

from apps.compose.views import compose_forward, compose_new, compose_reply, compose_send

app_name = "compose"

urlpatterns = [
    path("", compose_new, name="new"),
    path("send/", compose_send, name="send"),
    path("reply/<path:folder_name>/<int:uid>/", compose_reply, name="reply"),
    path("forward/<path:folder_name>/<int:uid>/", compose_forward, name="forward"),
]
