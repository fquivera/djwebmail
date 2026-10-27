# Production deployment guide

DjWebmail is deployed as a stateless WSGI web application (`config.wsgi:application`)
behind a TLS-terminating reverse proxy. Mail remains on your IMAP server;
PostgreSQL stores per-account UI preferences and Redis stores server-side
sessions, Fernet-encrypted IMAP credentials, login throttle counters, and
transient compose drafts/attachments.

---

## 1. Runtime topology

```text
Browser (HTTPS)
   │
   ▼
Reverse proxy (Caddy / Nginx / Traefik)
   │  X-Forwarded-Proto: https
   ▼
DjWebmail container (Gunicorn + WhiteNoise, port 8000, non-root user `django`)
   ├──► PostgreSQL 16+   (DATABASE_URL — preferences & Django metadata)
   ├──► Redis 7+         (REDIS_URL — sessions, encrypted credentials, drafts)
   └──► Mail server      (IMAPS 993 / Submission 587)
```

Key properties of the production container (`Dockerfile`):

- Built from `python:3.12-slim` using `uv sync --no-dev --group production`.
- Compiles Tailwind CSS + daisyUI and runs `collectstatic` during the image
  build; Node.js and the Tailwind binary are not shipped in the runtime image.
- Runs as the unprivileged `django` user on port `8000`.
- Exposes `/health/` for container and load-balancer liveness probes
  (`SECURE_REDIRECT_EXEMPT` allows `/health/` over plain HTTP inside the
  container network).

---

## 2. Required environment variables

`config.settings.production` fails fast at startup if any of the following
variables are missing or invalid:

| Variable | Description | Example |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Must be `config.settings.production` | `config.settings.production` |
| `DJANGO_SECRET_KEY` | High-entropy secret for CSRF and signing | *(50+ random chars)* |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated public hostnames plus loopback for container healthcheck | `mail.example.com,127.0.0.1,localhost` |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated HTTPS origins | `https://mail.example.com` |
| `DATABASE_URL` | PostgreSQL connection URL | `postgres://djwebmail:secret@db:5432/djwebmail` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `FERNET_KEY` | URL-safe base64 32-byte key for session credential encryption | *(44-char Fernet key)* |

Generate `DJANGO_SECRET_KEY` and `FERNET_KEY` once per deployment and store
them in your secret manager:

```bash
# DJANGO_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(50))"

# FERNET_KEY
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> **Note on `FERNET_KEY` rotation:** rotating `FERNET_KEY` invalidates active
> encrypted IMAP credentials in Redis, which cleanly signs out current sessions
> and prompts users to sign in again. No database data is encrypted with
> `FERNET_KEY`.

---

## 3. Mail server and application settings

Configure the upstream IMAP and SMTP endpoints via environment variables:

| Variable | Default | Description |
|---|---|---|
| `DJANGO_MAIL_DOMAIN` | `""` | Default domain appended when users sign in with a bare local-part |
| `DJANGO_MAIL_IMAP_HOST` | `""` | IMAP server hostname (e.g. `imap.example.com`) |
| `DJANGO_MAIL_IMAP_PORT` | `993` | IMAP server port |
| `DJANGO_MAIL_IMAP_SECURITY` | `ssl` | `ssl` (IMAPS), `starttls`, or `none` |
| `DJANGO_MAIL_SMTP_HOST` | `""` | SMTP submission hostname (e.g. `smtp.example.com`) |
| `DJANGO_MAIL_SMTP_PORT` | `587` | SMTP submission port |
| `DJANGO_MAIL_SMTP_SECURITY` | `starttls` | `starttls`, `ssl`, or `none` |
| `DJANGO_MAIL_VERIFY_TLS` | `True` | Verify IMAP/SMTP TLS certificates (keep `True` in production) |
| `DJANGO_MAIL_TIMEOUT_SECONDS` | `30` | Socket timeout for IMAP and SMTP operations |

Optional operational tuning:

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SESSION_COOKIE_AGE` | `28800` | Absolute session lifetime in seconds (8 hours) |
| `DJANGO_MAIL_DEFAULT_PAGE_SIZE` | `50` | Default messages per page |
| `DJANGO_MAIL_MAX_PAGE_SIZE` | `200` | Maximum allowed per-account page size |
| `DJANGO_MAIL_LOGIN_MAX_ATTEMPTS` | `5` | Failed login attempts before throttling |
| `DJANGO_MAIL_LOGIN_WINDOW_SECONDS` | `300` | Login throttle window in seconds |
| `DJANGO_MAIL_IMAGE_PROXY_MAX_BYTES` | `5000000` | Maximum remote image size fetched by the proxy (5 MB) |
| `DJANGO_MAIL_IMAGE_PROXY_TIMEOUT_SECONDS` | `10` | Timeout per proxied remote image request |
| `DJANGO_MAIL_MAX_ATTACHMENT_BYTES` | `25000000` | Maximum size of a single compose attachment (25 MB) |
| `DJANGO_MAIL_MAX_ATTACHMENTS_TOTAL_BYTES` | `25000000` | Maximum combined size of compose attachments (25 MB) |
| `DJANGO_MAIL_MAX_ATTACHMENTS` | `10` | Maximum number of attachments per draft |
| `DJANGO_MAIL_COMPOSE_TTL_SECONDS` | `3600` | Redis TTL for compose drafts and uploaded attachments |
| `DJANGO_MAIL_ACCOUNTS_FILE` | `""` | Optional mounted accounts file path (e.g. `postfix-accounts.cf` for `docker-mailserver`) |
| `DJANGO_MAIL_POPPASSD_HOST` | `""` | Optional POPPASSD daemon hostname for remote password updates |
| `DJANGO_MAIL_POPPASSD_PORT` | `106` | POPPASSD daemon port |
| `DJANGO_MAIL_CHANGE_PASSWORD_ENABLED` | `True` | Enable/disable self-service password changes |
| `DJANGO_LANGUAGE_CODE` | `en-us` | Fallback UI language before a user preference is loaded |
| `DJANGO_LOG_LEVEL` | `INFO` | Root/application log level (`INFO`, `WARNING`, `ERROR`) |

---

## 4. Docker Compose production example

Tagged releases publish multi-platform images to GitHub Container Registry at
`ghcr.io/fquivera/djwebmail:<version>`.

Create a `.env.prod` file (mode `0600`, never committed to Git):

```dotenv
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY=replace-with-generated-secret-key
DJANGO_ALLOWED_HOSTS=mail.example.com,127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=https://mail.example.com
FERNET_KEY=replace-with-generated-fernet-key

POSTGRES_DB=djwebmail
POSTGRES_USER=djwebmail
POSTGRES_PASSWORD=replace-with-strong-db-password
DATABASE_URL=postgres://djwebmail:replace-with-strong-db-password@db:5432/djwebmail
REDIS_URL=redis://redis:6379/0

DJANGO_MAIL_DOMAIN=example.com
DJANGO_MAIL_IMAP_HOST=imap.example.com
DJANGO_MAIL_IMAP_PORT=993
DJANGO_MAIL_IMAP_SECURITY=ssl
DJANGO_MAIL_SMTP_HOST=smtp.example.com
DJANGO_MAIL_SMTP_PORT=587
DJANGO_MAIL_SMTP_SECURITY=starttls
DJANGO_MAIL_VERIFY_TLS=True
```

Example `compose.prod.yml`:

```yaml
name: djwebmail-prod

services:
  db:
    image: postgres:16
    restart: unless-stopped
    env_file: .env.prod
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  web:
    image: ghcr.io/fquivera/djwebmail:0.2.1
    restart: unless-stopped
    env_file: .env.prod
    command:
      - sh
      - -c
      - python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

volumes:
  postgres_data:
  redis_data:
```

Start the stack:

```bash
docker compose -f compose.prod.yml up -d
```

---

## 5. Reverse proxy configuration

`config.settings.production` expects TLS termination at the reverse proxy and
trusts `X-Forwarded-Proto: https` (`SECURE_PROXY_SSL_HEADER`). Bind the `web`
container only to `127.0.0.1:8000` (or an internal Docker network) so external
clients cannot spoof `X-Forwarded-Proto`.

### Caddy

```caddyfile
mail.example.com {
    encode zstd gzip
    request_body {
        max_size 30MB
    }
    reverse_proxy 127.0.0.1:8000
}
```

### Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name mail.example.com;

    # TLS certificates configured here...

    client_max_body_size 30m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 65s;
    }
}
```

> Set `client_max_body_size` (Nginx) or `request_body max_size` (Caddy) slightly
> above `DJANGO_MAIL_MAX_ATTACHMENTS_TOTAL_BYTES` so multipart attachment
> uploads reach Django cleanly.

---

## 6. Pre-flight verification and upgrades

### Pre-flight security check

Verify Django's deployment checks inside the container:

```bash
docker compose -f compose.prod.yml exec web python manage.py check --deploy
```

Verify the health endpoint:

```bash
curl -fsS https://mail.example.com/health/
```

### Upgrading

1. Back up the PostgreSQL database (`pg_dump`).
2. Update the image tag in `compose.prod.yml` (e.g. `ghcr.io/fquivera/djwebmail:0.2.0`).
3. Pull and recreate the container:
   ```bash
   docker compose -f compose.prod.yml pull web
   docker compose -f compose.prod.yml up -d web
   ```
   The startup command applies any new migrations (`python manage.py migrate --noinput`)
   before launching Gunicorn.
