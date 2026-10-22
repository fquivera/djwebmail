---
name: django-extensions
description: Django-extensions management commands for project introspection, debugging, and development. Use when exploring URLs, models, settings, database schema, running scripts, or profiling performance. Triggers on questions about Django project structure, model fields, URL routes, or requests to run development servers.
---

# Django Extensions

This project uses `django-extensions` and `uv`. Every command below runs from
the project root.

## Introspection

### Show URL Routes
```bash
uv run python manage.py show_urls
```

### List Model Information
```bash
# All models
uv run python manage.py list_model_info

# Specific model with signatures and field classes
uv run python manage.py list_model_info --model mail.Message --signature --field-class

# All methods including private
uv run python manage.py list_model_info --model mail.Message --all-methods --signature
```

### Print Settings
```bash
# All settings
uv run python manage.py print_settings --format=pprint

# Wildcards supported
uv run python manage.py print_settings AUTH*
uv run python manage.py print_settings DATABASE*
uv run python manage.py print_settings "*_DIRS"
```

### Show Permissions
```bash
uv run python manage.py show_permissions
uv run python manage.py show_permissions <app_label>
```

### Show Template Tags
```bash
uv run python manage.py show_template_tags
```

## Development

### Enhanced Shell (shell_plus)
```bash
uv run python manage.py shell_plus
uv run python manage.py shell_plus --print-sql
```
Auto-imports all models. Use `--dont-load app1` to skip apps.

### Enhanced Dev Server (runserver_plus)
```bash
uv run python manage.py runserver_plus
uv run python manage.py runserver_plus --print-sql
```
Includes the Werkzeug debugger for interactive debugging.

## Database

### SQL Diff (Compare Models to Schema)
```bash
uv run python manage.py sqldiff -a        # SQL differences
uv run python manage.py sqldiff -a -t     # Text differences (readable)
```

## Script Execution

### Run Scripts with Django Context
```bash
uv run python manage.py runscript <script_name>
uv run python manage.py runscript <script_name> --script-args arg1 arg2
uv run python manage.py runscript <script_name> --traceback
```
Scripts in `scripts/` must define a `run()` function.

## Profiling

### Profile Server Requests
```bash
uv run python manage.py runprofileserver --prof-path=/tmp/profiles
uv run python manage.py runprofileserver --use-cprofile --prof-path=/tmp/profiles
uv run python manage.py runprofileserver --kcachegrind --prof-path=/tmp/profiles
```

## Notes

- Model notation: `app.ModelName` (e.g., `accounts.EmailAccount`, `mail.Message`)
- Settings wildcards: `AUTH*`, `*_DIRS`, `DATABASE*`
- If a command is missing, confirm `django_extensions` is in `INSTALLED_APPS`

## Integration with Other Skills

- **django-patterns**: verify routes and app boundaries
- **django-models**: inspect fields, methods, and indexes
- **systematic-debugging**: `shell_plus --print-sql` to reproduce query bugs
- **htmx-patterns**: confirm the URL names used by `hx-get`/`hx-post`
