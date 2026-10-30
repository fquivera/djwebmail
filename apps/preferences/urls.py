"""URL routes for account preferences."""

from django.urls import path

from apps.preferences.views import (
    index,
    password_change_view,
    signature_delete,
    signature_modal,
    signature_save,
    signature_set_default,
    signature_toggle_active,
    signatures_panel,
)

app_name = "preferences"

urlpatterns = [
    path("", index, name="index"),
    path("password/", password_change_view, name="password"),
    path("signatures/", signatures_panel, name="signatures_panel"),
    path("signatures/modal/", signature_modal, name="signature_modal"),
    path("signatures/save/", signature_save, name="signature_save"),
    path(
        "signatures/<int:sig_id>/default/",
        signature_set_default,
        name="signature_set_default",
    ),
    path(
        "signatures/<int:sig_id>/toggle/",
        signature_toggle_active,
        name="signature_toggle_active",
    ),
    path("signatures/<int:sig_id>/delete/", signature_delete, name="signature_delete"),
]
