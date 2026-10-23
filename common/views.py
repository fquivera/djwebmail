"""Views shared across the project."""

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render


def home(request: HttpRequest) -> HttpResponse:
    """Temporary landing page until the mail UI exists."""
    return render(request, "common/home.html")


def health(request: HttpRequest) -> JsonResponse:
    """Liveness probe used by the container healthcheck."""
    return JsonResponse({"status": "ok"})
