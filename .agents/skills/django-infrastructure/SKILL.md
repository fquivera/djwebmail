---
name: django-infrastructure
description: Production infrastructure and project-structure patterns for Django. Use when setting up a project layout, splitting settings per environment, configuring Docker or Gunicorn, separating requirements, or reviewing production readiness of a Django deployment.
---

# Django Infrastructure Patterns

Reference for structuring Django projects that are ready for production: clear
separation of responsibilities, explicit layers, and reproducible deployments.

> Business-logic placement is defined once in **django-models → "Canonical
> boundary: models vs services"**. This skill only covers project layout,
> configuration, and deployment.

## 1. Separate Configuration from Domain Code

Never mix project configuration with business logic. Use a `config/` package
instead of a monolithic `settings.py`.

```text
myproject/
├── config/                  # Project configuration (NOT an app)
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   ├── production.py
│   │   ├── staging.py
│   │   └── test.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── apps/                    # All domain apps
├── common/                  # Shared utilities, templatetags, base templates
├── requirements/
├── manage.py
└── pyproject.toml
```

**Rule:** `django-admin startproject config .` (note the trailing dot) to avoid
a duplicated project folder.

## 2. Apps as Bounded Contexts

Each app must map to **one domain noun**. Names like `core`, `utils`, or
`helpers` are warning signs because they accumulate unrelated code.

```text
apps/users/       apps/orders/       apps/payments/
```

**Dependency direction:** apps must form a DAG. `orders` may import from
`users`; `users` must never import from `orders`. Enforce it with an import
linter (ruff `flake8-tidy-imports` or `import-linter`), not by convention alone.

Cross-app reads belong in selectors; cross-app writes belong in services.

## 3. Service Layer for Use Cases

Views and serializers never contain business logic. Orchestration lives in
`services.py`; reusable reads live in `selectors.py`.

```python
# apps/orders/services.py
from django.db import transaction
from apps.orders.models import Order

class OrderService:
    @staticmethod
    @transaction.atomic
    def create_order(user, items_data) -> Order:
        # Cross-aggregate workflow: stock, payment, notification
        ...
```

```python
# apps/orders/views.py — THIN
from rest_framework.views import APIView
from apps.orders.services import OrderService

class OrderCreateView(APIView):
    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = OrderService.create_order(
            user=request.user,
            **serializer.validated_data,
        )
        return Response({"id": order.id}, status=201)
```

**Benefit:** logic is testable without an HTTP request and reusable from Celery
tasks, management commands, and management actions.

## 4. Selector Layer for Queries

Separate reads (selectors) from writes (services). Selectors encapsulate
`select_related`/`prefetch_related` so every caller gets the same optimized query.

```python
# apps/orders/selectors.py
from django.db.models import QuerySet
from apps.orders.models import Order

def get_orders_for_user(user_id: int) -> QuerySet[Order]:
    return (
        Order.objects
        .filter(user_id=user_id)
        .select_related("user")
        .prefetch_related("items__product")
        .order_by("-created_at")
    )
```

## 5. Thin Models, No Complex Inheritance

Models keep field definitions, constraints, indexes, and **row-level**
invariants. Orchestration goes to services; see the canonical boundary table in
`django-models`.

```python
import uuid
from django.db import models

# ✅ Abstract base model for shared fields
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class Order(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="orders")
    status = models.CharField(max_length=20)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "status"])]
```

**Rule:** if a model method exceeds ~10 lines or branches on workflow state,
move it to a service. Do not create multi-table inheritance hierarchies for
domain modeling.

## 6. Configuration per Environment (No Conditionals in Settings)

Use `django-environ` and environment variables. Never use `if DEBUG:` to switch
databases or backends.

```python
# config/settings/base.py
import environ
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
DATABASES = {"default": env.db("DATABASE_URL")}
```

```bash
# .env (local) — NEVER commit
DJANGO_SETTINGS_MODULE=config.settings.development
DATABASE_URL=postgres://user:pass@localhost:5432/mydb
DJANGO_SECRET_KEY=change-me
```

Commit `.env.example` with every required key and no real values.

## 7. Custom User Model on Day One

Define it before the first migration. Changing it later requires major surgery.

```python
# apps/users/models.py
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]
```

```python
# config/settings/base.py
AUTH_USER_MODEL = "users.User"
```

## 8. Dependencies per Environment

Separate `requirements/` by environment. Production must never install
`django-debug-toolbar`, `pytest`, or `ruff`.

```text
requirements/
├── base.txt          # Django, psycopg, django-environ
├── development.txt   # -r base.txt + debug-toolbar, pytest, ruff, pyright
└── production.txt    # -r base.txt + gunicorn, whitenoise
```

With `uv`, keep the same split through dependency groups in `pyproject.toml`.

## 9. Migrations: Never Edit Applied Migrations

Applied migrations are immutable. For schema changes:

1. Create a new migration with a descriptive name:
   `uv run python manage.py makemigrations --name add_status_index_to_orders`
2. Review the SQL: `uv run python manage.py sqlmigrate app_name 0001`
3. Keep data migrations (`RunPython`) separate from schema migrations
4. Always provide a `reverse` function in `RunPython`

## 10. Docker and Production: Multi-stage + Non-root User

The production `Dockerfile` must use multi-stage builds and run as a non-root user.

```dockerfile
FROM python:3.12-slim AS builder
# ... install build dependencies and wheels

FROM python:3.12-slim AS production
# ... copy only runtime artifacts
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
RUN addgroup --system django \
    && adduser --system --ingroup django django
USER django
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
```

**Rule:** never `runserver` in production. Use Gunicorn or Uvicorn.

## 11. Local Compose Stacks and Disposable Dependencies

Keep development, staging, and production reproducible without adding local
state to the application:

```text
Dockerfile          # production: multi-stage, non-root, Gunicorn
Dockerfile.dev      # development: dev dependencies, bind-mounted source
compose.yml         # Django + PostgreSQL + Redis + disposable mail server
compose.staging.yml # production image + staging settings + same mail server
```

- Development uses `config.settings.development`; staging uses
  `config.settings.staging`, which imports production and relaxes HTTPS-only
  behavior for loopback HTTP.
- Do not put test mail accounts or functional-test switches in application
  code. Compose supplies them through environment variables, and the test
  suite skips when they are absent.
- Pin disposable service images (for example `greenmail/standalone:2.1.14`)
  and add healthchecks so application startup does not race the dependency.
- A local mail server is not production infrastructure. Document its limits
  and never expose staging ports publicly.
- Use a separate `Dockerfile.dev`; production images must not contain pytest,
  Ruff, Pyright, or debug tooling.

## Verification Checklist

| Area | Check |
|---|---|
| Configuration | `config/settings/` with base, development, production, test |
| Apps | Domain apps under `apps/`, no `utils`/`helpers` catch-alls |
| Logic | No business logic in `views.py` or `serializers.py` |
| Boundary | Cross-aggregate logic in `services.py`, not model methods |
| Reads | Complex queries in `selectors.py` with `select_related`/`prefetch_related` |
| Models | Inherit `TimeStampedModel`, UUID PK, explicit indexes |
| User | `AUTH_USER_MODEL` set before the first migration |
| Dependencies | Split by environment; production has no dev packages |
| Docker | Multi-stage build, non-root user, Gunicorn in `CMD` |
| Local stack | `compose.yml` / `compose.staging.yml` validate and dependencies are healthy |
| Secrets | Only in `.env` (git-ignored); `.env.example` committed |

## Anti-Patterns to Avoid

- A single `settings.py` with `if DEBUG:` conditionals everywhere
- Business logic in `views.py` or `serializers.py`
- Cross-aggregate workflows inside model methods
- Apps named `core`, `utils`, or `helpers`
- Circular dependencies between apps
- `DEBUG=True` in production because an env var was missing
- Migrations edited by hand after being applied
- `runserver` in production
- Shipping dev/test dependencies in the production image
- Publishing a staging stack or using it with real mail

## Integration with Other Skills

- **django-models**: model/service boundary (canonical)
- **django-patterns**: application layering and services/selectors
- **django-expert**: deeper security, performance, and deployment references
- **celery-patterns**: background workers in production
- **code-quality**: pre-deploy audit
