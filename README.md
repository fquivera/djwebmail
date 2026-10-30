# DjWebmail

[![CI](https://github.com/fquivera/djwebmail/actions/workflows/ci.yml/badge.svg)](https://github.com/fquivera/djwebmail/actions/workflows/ci.yml)
[![Release](https://github.com/fquivera/djwebmail/actions/workflows/release.yml/badge.svg)](https://github.com/fquivera/djwebmail/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Docker Image](https://img.shields.io/badge/ghcr.io-djwebmail-green.svg)](https://github.com/fquivera/djwebmail/pkgs/container/djwebmail)

**A modern, lightweight, server-rendered webmail client built with Django, HTMX, and Tailwind CSS.**

DjWebmail connects directly to your existing IMAP and SMTP servers. It delivers a fast, responsive user experience without heavy single-page application (SPA) frameworks or complex browser build pipelines.

Inspired by [SnappyMail](https://github.com/the-djmaze/snappymail) and Roundcube, but rebuilt from scratch in Python and Django with an HTMX-first architecture.

---

## Key Features

### ✉️ Email Experience
- **IMAP as Source of Truth**: Emails and folders live strictly on your IMAP server; no email message data is stored in the local database.
- **Continuous IMAP Draft Autosave**: Drafts save automatically to your server's `Drafts` (or `Borradores`) mailbox as you type, with live indicators and seamless draft editing.
- **Rich-Text Compose**: Multi-recipient handling (`To`, `Cc`, `Bcc`), rich HTML formatting, inline pasted/dropped images, multiple signatures, and attachment streaming.
- **Fast 3-Pane Interface**: Full 100vh responsive layout with folder trees, unread badges, multi-message batch actions, and unified search.
- **Security & Privacy First**: Server-side HTML sanitization with `nh3`, anti-SSRF remote image proxy, strict Content Security Policy (CSP), and zero client-side credential storage.
- **Strict Attachment Viewer**: Built-in modal preview for images, PDFs, text, and media without leaving the mailbox.

### ⚙️ Mailbox Control & Automation
- **ManageSieve Filters (RFC 5228 / RFC 5804)**: Visual rule builder for incoming email filtering (move, discard, forward, flag), backed directly by Dovecot/ManageSieve or an automatic database fallback.
- **Vacation Auto-Responder**: Out-of-office auto-reply configuration with customizable subject, body, interval days, and active status.
- **Sender Rules**: Per-account allowlist for trusted senders (automatic image display) and denylist for blocked senders.
- **RFC 7095 jCard Contacts**: Full contact management with JSON jCard import/export, autocomplete in compose, and one-click contact addition from message headers.

### 🛡️ Administration & Domain Management (`mailadmin`)
- **Multi-Driver Architecture**: Native drivers for `docker-mailserver` and standard file-based accounts (`postfix_accounts` / `postfix_virtual`), with extensible driver support.
- **Accounts & Quota Visibility**: Real-time storage consumption metrics, account creation/suspension, and password updates.
- **Virtual Aliases & Distribution Lists**: Manage alias forwarders, group distribution lists, and catch-all rules directly from the web UI.
- **Corporate Branding**: Configurable organization name, custom logos, browser favicon, and helpdesk support links.
- **Diagnostics Dashboard**: Built-in health probes verifying database, cache, IMAP, SMTP, and ManageSieve connectivity.

---

## Quickstart with Docker Compose

The fastest way to deploy DjWebmail is using the official Docker image from GitHub Container Registry: `ghcr.io/fquivera/djwebmail:latest`.

### 1. Standalone Stack (Caddy + DjWebmail + PostgreSQL + Redis)

Create a `compose.yml` file:

```yaml
services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - web

  web:
    image: ghcr.io/fquivera/djwebmail:latest
    restart: unless-stopped
    env_file: .env
    volumes:
      - media_data:/app/media
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: djwebmail
      POSTGRES_USER: djwebmail
      POSTGRES_PASSWORD: ChangeThisPostgresPassword
    volumes:
      - db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U djwebmail"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  db_data:
  redis_data:
  media_data:
  caddy_data:
  caddy_config:
```

### 2. Configure Environment (`.env`)

Generate required keys:

```bash
# Secret key for Django signing
python3 -c "import secrets; print(secrets.token_urlsafe(50))"

# Fernet key for encrypting IMAP credentials in memory
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Save your `.env` configuration:

```env
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=your-generated-secret-key
FERNET_KEY=your-generated-fernet-key
DJANGO_ALLOWED_HOSTS=mail.example.com,web,localhost
CSRF_TRUSTED_ORIGINS=https://mail.example.com

DATABASE_URL=postgres://djwebmail:ChangeThisPostgresPassword@db:5432/djwebmail
REDIS_URL=redis://redis:6379/0

# Mail server connection
DJANGO_MAIL_IMAP_HOST=mail.example.com
DJANGO_MAIL_IMAP_PORT=993
DJANGO_MAIL_IMAP_SECURITY=ssl

DJANGO_MAIL_SMTP_HOST=mail.example.com
DJANGO_MAIL_SMTP_PORT=587
DJANGO_MAIL_SMTP_SECURITY=starttls

# Optional: ManageSieve for server-side filter rules
DJANGO_MAIL_MANAGESIEVE_ENABLED=True
DJANGO_MAIL_MANAGESIEVE_HOST=mail.example.com
DJANGO_MAIL_MANAGESIEVE_PORT=4190
DJANGO_MAIL_MANAGESIEVE_SECURITY=starttls
DJANGO_MAIL_VERIFY_TLS=True

# Admin Module (Optional)
DJANGO_MAIL_ADMIN_ACCOUNTS=admin@example.com
```

### 3. Caddy Reverse Proxy (`Caddyfile`)

```caddyfile
mail.example.com {
    reverse_proxy web:8000 {
        header_up Host {host}
        header_up X-Forwarded-Proto https
    }
}
```

### 4. Start the Application

```bash
docker compose up -d
docker compose exec web python manage.py migrate
```

Visit `https://mail.example.com` to log in with your email account!

---

## Configuration Reference

| Environment Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.development` | Set to `config.settings.production` in live environments. |
| `DJANGO_SECRET_KEY` | *(None)* | High-entropy secret for signing and CSRF tokens. |
| `FERNET_KEY` | *(None)* | URL-safe base64 32-byte key used to encrypt the session IMAP credentials in Redis. |
| `DATABASE_URL` | `sqlite:///db.sqlite3` | PostgreSQL connection URL (e.g., `postgres://user:pass@host:5432/db`). |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis instance for session state, credential caching, and temporary attachments. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated list of allowed hostnames. |
| `CSRF_TRUSTED_ORIGINS` | *(None)* | Comma-separated list of trusted HTTPS origins (e.g., `https://mail.example.com`). |
| `DJANGO_MAIL_IMAP_HOST` | `localhost` | Hostname or IP of your IMAP server. |
| `DJANGO_MAIL_IMAP_PORT` | `993` | IMAP port (typically 993 for SSL/TLS, 143 for STARTTLS). |
| `DJANGO_MAIL_IMAP_SECURITY` | `ssl` | Connection security: `ssl`, `starttls`, or `plain`. |
| `DJANGO_MAIL_SMTP_HOST` | `localhost` | Hostname or IP of your SMTP server. |
| `DJANGO_MAIL_SMTP_PORT` | `587` | SMTP port (typically 587 for STARTTLS, 465 for SSL, 25 for plain). |
| `DJANGO_MAIL_SMTP_SECURITY` | `starttls` | Connection security: `starttls`, `ssl`, or `plain`. |
| `DJANGO_MAIL_MANAGESIEVE_HOST`| *(None)* | ManageSieve server host (e.g., Dovecot ManageSieve on port 4190). |
| `DJANGO_MAIL_MANAGESIEVE_PORT`| `4190` | Port for ManageSieve protocol. |
| `DJANGO_MAIL_MANAGESIEVE_ENABLED` | `False` | Enables direct Sieve script synchronization over ManageSieve. |
| `DJANGO_MAIL_ADMIN_ACCOUNTS` | *(None)* | Comma-separated list of email addresses granted access to `/mailadmin/`. |
| `DJANGO_MAIL_ADMIN_DRIVER` | `docker-mailserver` | Driver for admin operations: `docker-mailserver`, `file`, or `none`. |

Detailed deployment guides and Nginx configurations are documented in [`docs/deployment.md`](docs/deployment.md).

---

## Bare-Metal Deployment (Systemd + Gunicorn)

For non-containerized installations on Debian/Ubuntu:

```bash
# 1. Clone & sync dependencies
git clone https://github.com/fquivera/djwebmail.git /opt/djwebmail
cd /opt/djwebmail
uv sync --no-dev --group production

# 2. Configure .env and migrate
cp .env.example .env
# Edit .env with your secrets and database credentials
uv run python manage.py migrate
uv run python manage.py collectstatic --no-input

# 3. Run with Gunicorn
uv run gunicorn config.wsgi:application \
    --bind 127.0.0.1:8000 \
    --workers 4 \
    --timeout 60
```

Refer to [`docs/deployment.md`](docs/deployment.md) for full Systemd unit files and automated restart configuration.

---

## Architecture & Technology Stack

| Layer | Component | Choice |
|---|---|---|
| **Backend** | Framework | Django 5.2 LTS |
| **Interactivity** | Hypermedia | HTMX (server-rendered dynamic fragments) |
| **Local State** | UI reactivity | Alpine.js (modals, dropdowns, keyboard navigation) |
| **Styling** | CSS System | Tailwind CSS + daisyUI (committed compiled CSS, no Node runtime) |
| **Mail Protocols** | IMAP / SMTP / Sieve | `imapclient`, Python `smtplib`, native ManageSieve RFC 5804 client |
| **Sanitization** | HTML Engine | `nh3` (Ammonia Rust-based parser) |
| **Storage** | Relational DB | PostgreSQL 16+ (preferences, metadata, jCards) |
| **Cache & Sessions**| In-memory store | Redis 7+ (Fernet-encrypted credentials, drafts, throttles) |

---

## Contributing & Development

We welcome contributions from developers, designers, and translators!

- For developer setup, project philosophy, architectural decisions, and coding standards, check out [**CONTRIBUTING.md**](CONTRIBUTING.md).
- To report bugs or propose new features, please open an issue on [GitHub Issues](https://github.com/fquivera/djwebmail/issues).

---

## License

DjWebmail is open-source software licensed under the [MIT License](LICENSE).
