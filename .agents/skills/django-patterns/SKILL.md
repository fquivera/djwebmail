---
name: django-patterns
description: Django architecture patterns for layering, DRF APIs, caching, signals, and middleware. Use when designing a Django project structure, deciding where business logic belongs, adding an API layer, or wiring caching and middleware.
---

# Django Architecture Patterns

Architecture-level guidance and a router to the detailed skills and references.
Deep ORM, forms, testing, security, and deployment details live in their own
skills; do not duplicate them here.

## Where Does This Belong?

| Need | Use | Canonical source |
|---|---|---|
| Row-level invariants, state transitions | Model / QuerySet method | `django-models` |
| Multi-aggregate workflow, I/O, transactions | `services.py` | `django-models` → canonical boundary |
| Reusable optimized read | `selectors.py` | `django-infrastructure` |
| HTTP translation | View / serializer | `django-patterns` (this file) |
| Form validation | `forms.py` | `django-forms` |
| HTML fragments | Templates + `hx-*` | `django-templates`, `htmx-patterns` |
| Tests | `pytest` + factories | `pytest-django-patterns` |
| Deployment, settings split, Docker | `config/`, `requirements/` | `django-infrastructure` |

## Project Layout

```text
myproject/
├── config/
│   ├── settings/{base,development,production,test}.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   └── users/
│       ├── models.py
│       ├── selectors.py
│       ├── services.py
│       ├── views.py
│       ├── forms.py          # server-rendered UI
│       ├── serializers.py    # only if a DRF API exists
│       ├── urls.py
│       └── tests/
├── common/                   # templatetags, base templates, shared helpers
├── requirements/
├── manage.py
└── pyproject.toml
```

Use DRF only for endpoints consumed by clients other than the HTMX UI. A
server-rendered HTMX app does not need serializers for its own pages.

## Service Layer

Services orchestrate use cases; they never know about `request` or templates.

```python
# apps/orders/services.py
from django.db import transaction
from .models import Order

class OrderService:
    @staticmethod
    @transaction.atomic
    def create_order(user, cart) -> Order:
        order = Order.objects.create(user=user, total=cart.total_price)
        for item in cart.items.select_related("product"):
            order.items.create(
                product=item.product,
                quantity=item.quantity,
                price=item.product.price,
            )
        cart.items.all().delete()
        return order
```

Rules:

- `@transaction.atomic` on service methods, not on views.
- Return domain objects, not HTTP responses.
- Raise domain exceptions; map them to status codes in the view.
- Keep external calls (IMAP, SMTP, payments) behind an injectable interface so
  tests can replace them.

## Views

```python
# apps/orders/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from .exceptions import InsufficientStock  # domain exception
from .services import OrderService

@login_required
def create_order(request):
    if request.method != "POST":
        return render(request, "orders/create.html")
    try:
        order = OrderService.create_order(request.user, request.user.cart)
    except InsufficientStock:
        return render(request, "orders/_form.html", {"error": "Out of stock"}, status=422)

    if request.headers.get("HX-Request"):
        return render(request, "orders/_order.html", {"order": order})
    return redirect("orders:detail", pk=order.pk)
```

Views: authenticate, authorize, validate input, call one service/selector, render.
Nothing else.

## DRF APIs

Only when a non-HTML client exists. Full patterns:
`django-expert/references/drf-guidelines.md`.

```python
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from .filters import ProductFilter
from .serializers import ProductSerializer

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related("category").prefetch_related("tags")
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = ProductFilter
    search_fields = ["name", "description"]
```

- Separate read and write serializers when fields differ.
- Always paginate; always filter at the database.
- Never expose `fields = "__all__"` on models with sensitive columns.
- Version APIs before breaking changes.

## Caching

```python
from django.core.cache import cache
from django.db.models import Count

def get_popular_categories():
    key = "popular_categories"
    categories = cache.get(key)
    if categories is None:
        categories = list(
            Category.objects.annotate(product_count=Count("products"))
            .filter(product_count__gt=10)
            .order_by("-product_count")[:20]
        )
        cache.set(key, categories, timeout=60 * 60)
    return categories
```

- Cache only after measuring; optimize queries first.
- Never cache per-user HTML with `cache_page` — it leaks data across users.
- Invalidate explicitly in the service that mutates the data.
- Namespace keys (`mail:{user_id}:folders`).

## Signals

Prefer explicit calls. Signals are for reacting to changes you do not control
or for audit/cache side effects.

```python
# apps/users/apps.py
class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"

    def ready(self):
        from . import signals  # noqa: F401
```

```python
# apps/users/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Profile, User

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
```

- Never put workflow logic in signals: it runs on every save and hides call sites.
- If you own the trigger and the reaction, call the function directly.

## Middleware

```python
import logging
import time

logger = logging.getLogger(__name__)

class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        logger.info(
            "%s %s -> %s in %.3fs",
            request.method, request.path, response.status_code,
            time.perf_counter() - start,
        )
        return response
```

- Prefer the `__call__` form; `MiddlewareMixin` is legacy.
- Never mutate the database on every request (e.g. `last_active` writes).
- Keep middleware under ~10 ms; do heavy work in tasks.

## Performance Checklist

- `select_related` for FK/OneToOne, `prefetch_related` for reverse FK/M2M.
- `.exists()` / `.count()` instead of truthiness or `len()`.
- `only()`/`defer()` for wide tables; `values()` for read-only projections.
- Bulk operations (`bulk_create`, `bulk_update`) instead of loops.
- Index columns used in filters and ordering; verify with `EXPLAIN ANALYZE`.
- Use `CaptureQueriesContext` in tests to lock query counts.

## Quick Reference

| Pattern | Purpose |
|---|---|
| Split settings | Environment-specific configuration |
| `apps/` layout | Domain bounded contexts |
| Service layer | Use-case orchestration, transactions |
| Selector layer | Reusable optimized reads |
| Custom QuerySet | Chainable domain filters |
| Signals | External reactions only |
| Middleware | Request/response concerns |
| DRF | APIs for non-HTML clients |

## Integration with Other Skills

- **django-models**: field design, QuerySets, model/service boundary
- **django-forms**: validation and ModelForms
- **django-templates**: template structure and partials
- **htmx-patterns**, **htmx-alpine**: interactive UI
- **django-infrastructure**: layout, settings, deployment
- **pytest-django-patterns**: testing services and views
- **celery-patterns**: moving work out of the request cycle
