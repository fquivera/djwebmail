"""Smoke tests for the project shell."""

import pytest
from django.urls import reverse


def test_health_endpoint(client):
    response = client.get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_home_page_renders(client):
    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert b"DjWebmail" in response.content
    template_names = [template.name for template in response.templates]
    assert "common/home.html" in template_names
    assert "base.html" in template_names


@pytest.mark.django_db
def test_admin_login_page_renders(client):
    response = client.get("/admin/login/")

    assert response.status_code == 200
