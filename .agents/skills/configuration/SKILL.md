---
name: configuration
description: Configuration and anti-hardcoding rules for DjWebmail. Use when adding settings, environment variables, user preferences, feature flags, timeouts, limits, URLs, or any value that differs between environments.
---

# Configuration and Anti-Hardcoding

Deployment values come from the environment. User choices come from the
database. Stable domain facts come from a `constants.py` module. Application
code never embeds any of them.

## Three layers

| Layer | Examples | Where it lives | Who changes it |
|---|---|---|---|
| Deployment | secrets, hosts, DB/Redis URLs, IMAP/SMTP endpoints, TLS, log level | environment variables read in `config/settings/` | operator |
| User preference | language, time zone, theme, density, signature, page size | `apps/preferences` model + form | end user |
| Domain constant | IMAP `INBOX` name, MIME types, protocol limits, enum codes | `common/constants.py` or app `constants.py` | developer |

If a value can differ between two deployments, it is deployment config. If two
users can choose differently, it is a preference. If neither is true, it is a
constant.

## Environment variables

Canonical names (`.env.example` is the source of truth):

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | yes | `config.settings.development` in `manage.py` | settings module |
| `DJANGO_SECRET_KEY` | yes | — | Django signing key |
| `DJANGO_DEBUG` | no | `False` | debug mode; never true in production |
| `DJANGO_ALLOWED_HOSTS` | production | empty | comma-separated hostnames |
| `DJANGO_LANGUAGE_CODE` | no | `en-us` | fallback language |
| `DJANGO_LOG_LEVEL` | no | `INFO` | root log level |
| `DATABASE_URL` | no | SQLite in `BASE_DIR` | database DSN |
| `CSRF_TRUSTED_ORIGINS` | production | empty | comma-separated HTTPS origins |
| `DJANGO_MAIL_DOMAIN` | production | empty | mail domain for this deployment |
| `DJANGO_MAIL_IMAP_HOST` | production | empty | IMAP host |
| `DJANGO_MAIL_IMAP_PORT` | no | `993` | IMAP port |
| `DJANGO_MAIL_IMAP_SECURITY` | no | `ssl` | `ssl`, `starttls`, or `none` |
| `DJANGO_MAIL_SMTP_HOST` | production | empty | SMTP host |
| `DJANGO_MAIL_SMTP_PORT` | no | `587` | SMTP port |
| `DJANGO_MAIL_SMTP_SECURITY` | no | `starttls` | `ssl`, `starttls`, or `none` |
| `DJANGO_MAIL_VERIFY_TLS` | no | `True` | verify IMAP/SMTP certificates |
| `DJANGO_MAIL_TIMEOUT_SECONDS` | no | `30` | IMAP/SMTP socket timeout |
| `DJANGO_MAIL_DEFAULT_PAGE_SIZE` | no | `50` | default messages per page |
| `DJANGO_MAIL_MAX_PAGE_SIZE` | no | `200` | maximum accepted page size |
| `DJANGO_MAIL_LOGIN_MAX_ATTEMPTS` | no | `5` | failed logins before throttling |
| `DJANGO_MAIL_LOGIN_WINDOW_SECONDS` | no | `300` | login throttle window |
| `DJANGO_SESSION_COOKIE_AGE` | no | `28800` | absolute server-side session age |
| `REDIS_URL` | production | — | cache and encrypted credential storage |
| `FERNET_KEY` | production | — | encryption of transient IMAP credentials |

Rules:

- Add a variable to `config/settings/base.py`, `.env.example`, this table, and
  the deployment docs in the same change.
- No secret ever gets a real default. Development-only placeholders are clearly
  named and rejected by `config.settings.production`.
- Read variables with `django-environ` typed helpers (`env.str`, `env.bool`,
  `env.int`, `env.db_url_config`). Do not use `os.environ` or `os.getenv`
  outside `config/settings/`.
- Parse comma-separated lists explicitly and strip whitespace; do not rely on
  undocumented coercion.
- Environment variables win over `.env`. `.env` is a developer convenience and
  is never shipped in the image.

## Settings modules

```text
config/settings/
├── base.py          # shared defaults, reads env
├── development.py   # DEBUG=True, debug toolbar, permissive hosts
├── test.py          # fast hashers, test hosts, no external services
└── production.py    # fail-fast validation, HTTPS, WhiteNoise, HSTS
```

- `manage.py` defaults to `development`; `wsgi.py`/`asgi.py` default to
  `production`. `DJANGO_SETTINGS_MODULE` overrides both.
- `base.py` holds behavior shared by all environments; environment modules only
  override what differs.
- Do not branch on environment names inside application code
  (`if settings.DEBUG:` is acceptable for debug-only behavior, not for feature
  policy).
- Do not mutate `django.conf.settings` at runtime. Tests use
  `override_settings`.

## Fail fast

Production must refuse to start with incomplete configuration:

```python
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production")
```

- Validate required groups (mail, Redis, encryption) at startup with
  `django.core.checks` or `ImproperlyConfigured`.
- `manage.py check --deploy` runs in CI against production settings.
- Fail with an actionable message naming the variable, never with a stack trace
  that leaks the value.

## No hardcoding

Hardcoded means a value that belongs to one of the three layers is written
literally in application code.

Bad:

```python
IMAP_HOST = "imap.example.com"          # deployment value
TIMEOUT = 30                            # tunable
return redirect("/mail/inbox/")         # route
send_mail("no-reply@example.com", ...)  # deployment identity
if folder == "INBOX":                   # protocol fact, but duplicated
```

Good:

```python
# config/settings/base.py
MAIL_IMAP_HOST = env.str("DJANGO_MAIL_IMAP_HOST", default="")
MAIL_TIMEOUT_SECONDS = env.int("DJANGO_MAIL_TIMEOUT_SECONDS", default=30)

# common/constants.py
IMAP_INBOX = "INBOX"

# apps/mail/views.py
return redirect("mail:inbox")
```

Rules:

- Use `reverse()` and `{% url %}` for every internal route; never write
  `"/mail/..."` in Python or templates.
- Use `settings.X` for deployment values; import settings at call time or via
  `django.conf.settings`, not as a copied module constant.
- Use `constants.py` for protocol strings and enum codes; reference them instead
  of repeating literals.
- Timeouts, page sizes, upload limits, retry counts, and cache TTLs are
  configuration or constants — never inline numbers in services.
- Hostnames, IPs, ports, URLs, email addresses, and filesystem paths are never
  literals in `apps/`, `common/`, or `templates/`.
- User-visible strings are i18n messages, not configuration; see the `i18n`
  skill.
- Test fixtures may contain literals; tests are excluded from the scan.

## Templates

```django
{# bad #}
<a href="/mail/inbox/">Inbox</a>
<img src="https://cdn.example.com/logo.svg" alt="">

{# good #}
<a href="{% url 'mail:inbox' %}">{% translate "Inbox" %}</a>
<img src="{% static 'img/logo.svg' %}" alt="{% translate 'DjWebmail' %}">
```

External assets are served locally (CSP and privacy); if an exception is
unavoidable, document it with `{# hardcode-ok: reason #}`.

## User preferences

- Store choices in `apps/preferences`, never in settings or `.env`.
- Field defaults are constants, not magic values repeated in views.
- Validate with forms/choices; reject unknown values.
- Preferences are per user; deployment-wide defaults belong in settings.
- Changing a preference writes only that row; no global mutable state.

## Feature flags

```python
FEATURE_NEW_COMPOSER = env.bool("DJANGO_FEATURE_NEW_COMPOSER", default=False)
```

- Flags are deployment configuration, not user preferences, unless explicitly
  modeled per user.
- Default to off, document the removal condition, and delete the flag and dead
  branch after rollout.
- Never nest flags without a test for each combination that matters.

## CI enforcement

`scripts/check_hardcoding.py` runs as the required `hardcode-scan` job:

- reads `os.environ`/`os.getenv` outside `config/settings/`
- absolute URLs, loopback hosts, well-known ports, and absolute paths in code
- `print()` calls
- absolute `href`/`src`/`action`/`hx-*` paths in templates
- external URLs in templates

Suppress a justified line with a reason:

```python
DEFAULT_IMAP_PORT = 993  # hardcode-ok: protocol default, overridable by DJANGO_MAIL_IMAP_PORT
```

The marker is an exception, not a workaround. Reviewers reject markers without a
reason or with a value that should be configurable.

## Testing configuration

- `override_settings` for behavior that depends on a setting.
- Test that production validation rejects missing required variables.
- Test preference defaults, validation, and per-user isolation.
- Test that routes resolve through names, not literals.
- `manage.py check --deploy` must stay clean.

## Anti-Patterns

- `os.getenv` scattered through views or services
- A second configuration system (YAML/JSON) next to environment variables
- Secrets with defaults or committed `.env` files
- `settings.DEBUG` used to choose business behavior
- Hardcoded URLs, hosts, ports, emails, paths, timeouts, or limits
- Magic numbers in services (`if len(data) > 26214400`)
- Duplicated protocol strings (`"INBOX"`, `"\\Seen"`) across modules
- Storing user preferences in environment variables
- Changing `settings` at runtime
- Feature flags that never get removed
- Suppressing the scanner without a documented reason

## Integration with Other Skills

- **django-infrastructure**: settings split, Docker, production checklist
- **i18n**: language defaults and per-user language preference
- **django-models**: preference model fields, choices, and defaults
- **django-forms**: validation of user-provided configuration
- **django-patterns**: service boundaries and settings access
- **github-actions**: `hardcode-scan` job and required checks
