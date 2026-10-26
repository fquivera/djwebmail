"""URL routes for composing and sending mail."""

from django.urls import path

from apps.compose.views import (
    compose_attachment_delete,
    compose_attachments,
    compose_draft,
    compose_forward,
    compose_new,
    compose_reply,
    compose_reply_all,
    compose_send,
)

app_name = "compose"

urlpatterns = [
    path("", compose_new, name="new"),
    path("send/", compose_send, name="send"),
    path("draft/", compose_draft, name="draft"),
    path("attachments/", compose_attachments, name="attachments"),
    path(
        "attachments/<str:attachment_id>/delete/",
        compose_attachment_delete,
        name="attachment_delete",
    ),
    path("reply/<path:folder_name>/<int:uid>/", compose_reply, name="reply"),
    path("reply-all/<path:folder_name>/<int:uid>/", compose_reply_all, name="reply_all"),
    path("forward/<path:folder_name>/<int:uid>/", compose_forward, name="forward"),
]
