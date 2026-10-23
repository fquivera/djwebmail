# Tailwind and daisyUI build pipeline

DjWebmail compiles its CSS with `django-tailwind` in standalone mode. Node and
npm are not required in development, CI, or the production image.

## Pinned versions

| Component | Version | Source of truth |
|---|---|---|
| `django-tailwind` | 4.6.0 | `pyproject.toml` / `uv.lock` |
| Tailwind CSS standalone CLI | `v4.3.3` | `TAILWIND_STANDALONE_BINARY_VERSION` in `config/settings/base.py` |
| daisyUI | `v5.7.48` | `theme/static_src/src/daisyui*.mjs`, downloaded by the `django-tailwind` release |

The daisyUI plugin files are committed. Rebuilding does not depend on a remote
download when they are already present.

## Layout

```text
theme/
├── apps.py
├── __init__.py
├── static_src/
│   └── src/
│       ├── daisyui.mjs
│       ├── daisyui-theme.mjs
│       └── styles.css
└── static/css/dist/styles.css   # generated and committed
```

`theme` contains only generated CSS and build inputs. The application base
template lives in `templates/base.html`; the generated
`theme/templates/base.html` was removed so there is a single shell.

`styles.css` uses explicit `@source` globs for `templates/`, `apps/`, `common/`,
`config/`, and `static/js/`. Scoping the scan keeps virtualenvs, vendored
scripts, documentation, and generated output out of the CSS build.

The two daisyUI themes are `mail-light` (default) and `mail-dark`
(`prefersdark`). The first visit follows the operating-system preference. A
future user preference can render `data-theme="mail-light"` or
`data-theme="mail-dark"` on `<html>` from the server; no pre-paint script is
needed.

## Commands

```bash
# One-time regeneration of the theme app. The generated app is committed.
uv run --with cookiecutter python manage.py tailwind init \
  --no-input --app-name theme --tailwind-version 4s --include-daisy-ui

# Build the committed production CSS once.
DJANGO_SETTINGS_MODULE=config.settings.test uv run python manage.py tailwind build

# Watch templates and rebuild during frontend work.
DJANGO_SETTINGS_MODULE=config.settings.development uv run python manage.py tailwind start
```

`tailwind build` writes `theme/static/css/dist/styles.css`. The file is
committed because CI rebuilds it and fails when the committed output differs.
CI also fails when the gzip-compressed CSS exceeds the 60 KB budget.

## Django settings

```python
INSTALLED_APPS = [
    # ...
    "tailwind",
    "theme",
]

TAILWIND_APP_NAME = "theme"
TAILWIND_USE_STANDALONE_BINARY = True
TAILWIND_STANDALONE_BINARY_VERSION = "v4.3.3"
```

`theme` must remain after `tailwind`. `{% load tailwind_tags %}` and
`{% tailwind_css %}` in `templates/base.html` resolve
`css/dist/styles.css` through Django's static files.

## Deployment

`Dockerfile` runs `manage.py tailwind build` before `collectstatic`. The
standalone binary is downloaded to `/tmp/tailwindcss` and deleted after the
build so it is not copied into the runtime image. Production uses
`CompressedManifestStaticFilesStorage`, so the collected CSS has a content hash
and a manifest entry.

The CI `lint` job rebuilds the CSS and runs `git diff --exit-code` against the
committed file. A template class change without a rebuilt stylesheet fails
there instead of reaching production.

## Scope

This change delivers the build pipeline and the first daisyUI-based shell for
the home, login, mail folder, message-list, pagination, and error views. Strict
CSP, Alpine, the message viewer, and the compose UI are separate Phase 3 work.
