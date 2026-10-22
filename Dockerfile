# syntax=docker/dockerfile:1

# --- Build stage: resolve and install dependencies with uv -------------------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first so the layer is cached when only source code changes.
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --group production --no-install-project --no-editable

# --- Runtime stage: non-root, venv copied from the builder -------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN addgroup --system django \
    && adduser --system --ingroup django django

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY . .

RUN chown -R django:django /app

USER django

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=3)" || exit 1

# Gunicorn is in the production dependency group. collectstatic must run at
# deploy time once static assets exist.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
