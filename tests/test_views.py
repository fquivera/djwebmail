"""Smoke tests for the project shell."""

from typing import cast

import pytest
from django.http import HttpResponse
from django.test import Client
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


def test_login_page_keeps_same_origin_referrer_for_csrf(client):
    response = client.get(reverse("accounts:login"))

    assert response.headers["Referrer-Policy"] == "same-origin"


@pytest.mark.django_db
def test_null_origin_is_not_trusted():
    client = Client(enforce_csrf_checks=True)
    response = cast(HttpResponse, client.get(reverse("accounts:login")))
    token = response.cookies["csrftoken"].value

    response = cast(
        HttpResponse,
        client.post(
            reverse("accounts:logout"),
            {"csrfmiddlewaretoken": token},
            HTTP_ORIGIN="null",
        ),
    )

    assert response.status_code == 403
