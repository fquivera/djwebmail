# Development and staging stack

DjWebmail needs a real IMAP server for login and a real SMTP server for the
future compose flow. The repository ships two Docker Compose stacks backed by
[GreenMail](https://greenmail-mail-test.github.io/greenmail/), a disposable
mail server designed for integration tests.

## Why GreenMail instead of docker-mailserver

`docker-mailserver` is a complete production mail server. Running it locally
requires a hostname, TLS material, account provisioning, and privileged mail
ports. That is useful for validating a deployment, but it is heavy and
stateful for functional tests.

GreenMail provides deterministic IMAP/SMTP on unprivileged ports, accepts
preconfigured users, and starts in seconds. Application code still talks to a
normal IMAP/SMTP endpoint through environment variables, so replacing GreenMail
with `docker-mailserver` or a real server later does not require code changes.

The image is pinned to `greenmail/standalone:2.1.14`. It is not a production
mail server and must never receive real mail.

## Development stack

`compose.yml` runs:

| Service | Image | Purpose | Host port |
|---|---|---|---|
| `web` | `Dockerfile.dev` | Django development server | `8000` |
| `db` | `postgres:16` | PostgreSQL with a persistent volume | internal only |
| `redis` | `redis:7-alpine` | server-side session/cache storage | internal only |
| `mailserver` | `greenmail/standalone:2.1.14` | IMAP/SMTP test mailbox | `3143` / `3025` |

The GreenMail account is `demo@example.test` with password `demo`. It is a test
fixture, not a secret.

```bash
cp .env.example .env
# Set DJANGO_SECRET_KEY and FERNET_KEY in .env; see the file for generators.
docker compose up --build
```

Open <http://localhost:8000/> and sign in with the test account. The `web`
container runs migrations before starting the development server. The source
tree is bind-mounted, so Python and template edits reload automatically.

The stack enables `FUNCTIONAL_TESTS_ENABLED` and points the application at the
`mailserver` service. Run the functional suite inside the web container:

```bash
docker compose exec -e DJANGO_SETTINGS_MODULE=config.settings.test web pytest -m functional
```

Stop the stack with `docker compose down`; add `-v` to delete the PostgreSQL
and Redis volumes and start from a clean state.

### Connecting a mail client

To inspect the disposable mailbox with Thunderbird or another client:

| Setting | Value |
|---|---|
| IMAP host | `localhost` |
| IMAP port | `3143` |
| IMAP security | none |
| SMTP host | `localhost` |
| SMTP port | `3025` |
| SMTP security | none |
| Username | `demo@example.test` |
| Password | `demo` |

## Staging stack

`compose.staging.yml` uses the production `Dockerfile` (Gunicorn, WhiteNoise,
non-root user), PostgreSQL, Redis, and the same GreenMail service. It runs
`config.settings.staging`, which reuses the production settings and fail-fast
validation but disables HTTPS redirects, secure cookies, and HSTS so the stack
can be exercised over loopback HTTP.

```bash
cp .env.staging.example .env.staging
# Set DJANGO_SECRET_KEY and FERNET_KEY in .env.staging.
docker compose -f compose.staging.yml up --build
```

Open <http://localhost:8080/>. Host ports default to `8080` for the app,
`3144` for IMAP, and `3026` for SMTP, so the staging and development stacks can
run at the same time. Override `STAGING_WEB_PORT`, `STAGING_MAIL_IMAP_PORT`, or
`STAGING_MAIL_SMTP_PORT` when needed; if the web port changes, update
`CSRF_TRUSTED_ORIGINS` in `.env.staging` as well.

This stack is for local staging only. It is not a production deployment: do not
publish its ports, and use `config.settings.production` with HTTPS for a real
deployment. The production image does not include pytest; use the development
stack for the automated functional suite.

## Functional tests

`tests/functional/test_mail_stack.py` exercises the full Django request/view
layer with Django's test client and real IMAP/SMTP connections. It checks:

- login against GreenMail and creation of the server-side session;
- rejection of a wrong IMAP password;
- mailbox listing through `ImapService`;
- SMTP delivery followed by an IMAP fetch;
- logout clearing the mail session.

The tests are skipped unless `FUNCTIONAL_TESTS_ENABLED=True` and both
`DJANGO_MAIL_IMAP_HOST` and `DJANGO_MAIL_SMTP_HOST` are set. A normal
`uv run pytest` therefore never contacts a mailbox. The `functional` CI job
starts PostgreSQL and GreenMail services and runs:

```bash
uv run pytest -m functional
```

## Troubleshooting

- **Login returns “Mail sign-in is not configured.”** `FERNET_KEY` is missing or
  invalid in `.env`. Recreate the `web` container after changing `.env` so the
  process reads the new value.
- **Login returns 403 with “Origin checking failed - null …”.** Chromium sends
  `Origin: null` on same-origin form POSTs when the response uses
  `Referrer-Policy: no-referrer`. Keep `SECURE_REFERRER_POLICY = "same-origin"`
  and do not add `null` to `CSRF_TRUSTED_ORIGINS`.
- **Login returns “The mail server is unavailable.”** Check
  `docker compose ps`; the `mailserver` healthcheck must be healthy.
- **Functional tests skip.** They are disabled by default outside Compose. Set
  `FUNCTIONAL_TESTS_ENABLED=True` and configure the mail endpoints.
- **Port already in use.** Change `DJANGO_DEV_PORT`, `GREENMAIL_IMAP_PORT`,
  `GREENMAIL_SMTP_PORT`, or the corresponding `STAGING_*` variables.
