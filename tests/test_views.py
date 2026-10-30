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
    assert reverse("accounts:login").encode() in response.content
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


def test_media_file_serving(client, settings):
    media_dir = settings.MEDIA_ROOT / "branding"
    media_dir.mkdir(parents=True, exist_ok=True)
    test_file = media_dir / "logo.png"
    test_file.write_bytes(b"image-data")
    try:
        response = client.get(f"{settings.MEDIA_URL}branding/logo.png")
        assert response.status_code == 200
    finally:
        if test_file.exists():
            test_file.unlink()


@pytest.mark.django_db
def test_brand_wordmark_colors_rendered_on_public_views(client):
    brand_wordmark = '<span class="brand-dj">Dj</span><span class="brand-webmail">Webmail</span>'

    res_home = client.get(reverse("home"))
    assert res_home.status_code == 200
    home_html = res_home.content.decode("utf-8")
    assert brand_wordmark in home_html

    res_login = client.get(reverse("accounts:login"))
    assert res_login.status_code == 200
    login_html = res_login.content.decode("utf-8")
    assert brand_wordmark in login_html
    assert 'id="about-dialog"' in login_html
