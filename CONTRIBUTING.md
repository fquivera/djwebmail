# Contributing to DjWebmail

Thank you for your interest in contributing to **DjWebmail**! 

Whether you are fixing a bug, improving documentation, adding translations, or proposing new features, your help is welcome. This document explains the history, architecture, development workflow, and coding standards used across the project.

---

## 1. Project Background & Vision

DjWebmail was created to address a longstanding gap in self-hosted communication tools:
- **The Problem**: The majority of established webmail platforms are either written in legacy PHP codebases (Roundcube, SnappyMail) or structured as complex single-page applications (SPAs) with heavy client-side JavaScript frameworks, high memory consumption, and complex client-side state synchronization.
- **The Solution**: DjWebmail takes a **server-driven approach** using Python and **Django** with **HTMX** for partial page swaps, **Alpine.js** strictly for client-side ephemeral state (menus, modals, toggles), and **Tailwind CSS + daisyUI** for a compact, accessible UI.
- **The Outcome**: A fast, responsive, and auditable webmail that runs smoothly on modest hardware, keeps the mail protocol logic on the server, and provides a delightful developer experience.

---

## 2. Non-Negotiable Architecture Rules

Before writing code, please review these core tenets:

1. **IMAP is the Source of Truth**:
   - The database stores user preferences, jCard contacts, and deployment configuration—**never mail messages, folders, or flags**.
   - Do not create Django models for emails or mailboxes.
2. **Zero Hardcoding**:
   - Hosts, ports, URLs, timeouts, limits, email addresses, and secrets must **never** be hardcoded in views, models, services, or templates.
   - All runtime variables must be configurable via environment variables in `config/settings/base.py` and documented in `.env.example`.
   - Protocol strings belong in `common/constants.py` or `apps/<app>/constants.py`.
   - We enforce this automatically with `scripts/check_hardcoding.py`.
3. **Security First**:
   - End-user authentication is verified directly against IMAP; `django.contrib.auth` is strictly for internal staff/admin use.
   - The user's IMAP password **never** reaches the database, the browser, or disk logs. It is encrypted in Redis using Fernet, keyed strictly to the opaque session ID.
   - Strict Content Security Policy (CSP): no `unsafe-eval`, no `unsafe-inline`, and strict iframe/script sandboxing.
   - External images are rewritten through an anti-SSRF caching proxy (`/mail/image-proxy/`).
4. **Internationalization (i18n)**:
   - Source strings are always in English. Spanish is the primary first translation.
   - Every user-facing string must be translatable using `gettext` in Python and `{% translate %}` or `{% blocktranslate %}` in templates.
   - No string concatenation for user messages; use named format specifiers (e.g., `%(user)s`).
   - Translation catalogs live in `locale/es/LC_MESSAGES/django.po` and are compiled into `django.mo` using `python3 scripts/compile_mo.py`.

---

## 3. Local Development Setup

### Prerequisites
- **Python 3.12+**
- [**uv**](https://docs.astral.sh/uv/) (Extremely fast Python package and environment manager)
- **Docker & Docker Compose** (Optional, for running PostgreSQL, Redis, or GreenMail test servers)

### Quick Setup

```bash
# 1. Clone the repository
git clone https://github.com/fquivera/djwebmail.git
cd djwebmail

# 2. Install dependencies with uv
uv sync

# 3. Create your local .env configuration
cp .env.example .env

# 4. Generate a secret key and a Fernet key
uv run python -c "from cryptography.fernet import Fernet; print('FERNET_KEY=' + Fernet.generate_key().decode())"
# Paste this into your .env file along with a DJANGO_SECRET_KEY

# 5. Run migrations and start development server
uv run python manage.py migrate
uv run python manage.py runserver
```

Open your browser at `http://127.0.0.1:8000/`.

---

## 4. Frontend Asset Pipeline

DjWebmail uses **Tailwind CSS 4** and **daisyUI 5**. The compiled CSS is committed directly to git under `theme/static/css/dist/styles.css` so users can run DjWebmail without needing Node.js or npm.

If you modify templates or add new CSS utility classes, recompile the stylesheet:

```bash
# Build stylesheet once:
uv run python manage.py tailwind build

# Or run the watcher while developing:
uv run python manage.py tailwind start
```

---

## 5. Running Tests & Quality Checks

All Pull Requests must pass the automated quality suite in CI before merging.

### Automated Checks

Run the following commands locally before submitting a PR:

```bash
# 1. Unit & Integration Tests
uv run pytest -m "not functional"

# 2. Ruff Linter & Formatter
uv run ruff check .
uv run ruff format --check .

# 3. Static Type Analysis (Pyright)
uv run pyright

# 4. Django Checks & Migration Checks
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run

# 5. Anti-Hardcoding Audit
python3 scripts/check_hardcoding.py
```

### Running Functional Tests (with Disposable Mail Server)

We test real IMAP and SMTP interactions using GreenMail inside Docker:

```bash
# Start test stack (PostgreSQL, Redis, GreenMail)
docker compose up -d db redis greenmail

# Run functional test suite
DJANGO_SETTINGS_MODULE=config.settings.test uv run pytest -m functional
```

---

## 6. GitFlow & Contribution Workflow

This project strictly follows the **GitFlow** branching model:

```text
feature/<slug>  fix/<slug>  chore/*  docs/*
        │
        └──► PR into [ develop ] (Merged via Squash)

release/<x.y.z>  hotfix/<x.y.z>
        │
        └──► PR into [ main ] (Merged via Merge Commit)
                  │
                  └──► Back-merge into [ develop ]
```

### Pull Request Guidelines
1. **Branch off `develop`**:
   ```bash
   git switch develop
   git pull origin develop
   git switch -c feature/your-feature-name
   ```
2. **Commit Messages**: Follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat(mail): add draft auto-save to IMAP`
   - `fix(compose): preserve attachment on validation error`
   - `docs(deployment): add Nginx reverse proxy instructions`
3. **Open a PR**: Target the `develop` branch. Fill out the PR template completely.
4. **Squash & Merge**: Once approved and all CI checks pass, feature and fix branches are squashed and merged into `develop`.

---

## 7. Reporting Issues & Proposing Features

- **Bug Reports**: Open an issue describing the bug, reproduction steps, expected behavior, and your environment (mail server engine, Python version, Docker vs bare-metal).
- **Security Disclosures**: Please report security vulnerabilities privately by emailing the maintainer at `fquivera@gmail.com`.
- **Feature Requests**: Open a GitHub Discussion or Issue describing your use case and why it aligns with the project goals.

Thank you for contributing to DjWebmail!
