"""URL configuration for the RFC 7095 jCard contacts app."""

from django.urls import path

from apps.contacts import views

app_name = "contacts"

urlpatterns = [
    path("", views.index, name="index"),
    path("save/", views.save, name="create"),
    path("<int:contact_id>/save/", views.save, name="update"),
    path("<int:contact_id>/delete/", views.delete, name="delete"),
    path("export.json", views.export_jcard, name="export_jcard"),
    path("import/", views.import_jcard, name="import_jcard"),
]
