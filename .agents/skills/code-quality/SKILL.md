---
name: code-quality
description: Run code quality checks (ruff lint, ruff format, pyright, pytest) on a directory and report findings by severity. Use when the user wants to audit code quality, check for type errors, lint issues, or run automated checks on a path. Accepts a directory path as argument. Triggers on requests like "check code quality", "run quality checks", "/code-quality apps/".
---

# Code Quality Review

Review code quality in the directory provided by the user. This project uses
`uv` for all Python tooling.

## Instructions

1. **Identify files to review**:
   - Find all `.py` files in the directory
   - Exclude migrations, `__pycache__`, and generated files

2. **Run automated checks**:
   ```bash
   uv run ruff check <directory>
   uv run ruff format --check <directory>
   uv run pyright <directory>
   uv run pytest <directory> -v
   ```

   If a check is slow or unavailable, run the others and say so explicitly in the report.

3. **Manual review checklist**:
   - [ ] No `Any` types without justification
   - [ ] Proper error handling (no silent exceptions)
   - [ ] N+1 queries avoided (select_related/prefetch_related)
   - [ ] Business logic not in views; model/service boundary respected
   - [ ] Forms have proper validation
   - [ ] Views return correct HTTP status codes (form errors re-rendered with 200 by default)
   - [ ] HTMX partials check the `HX-Request` header and set `Vary`
   - [ ] CSRF header present on HTMX POSTs
   - [ ] Celery tasks are idempotent (if Celery is used)
   - [ ] Tests use factories, not raw object creation
   - [ ] No secrets in code or settings

4. **Report findings** organized by severity:
   - Critical (must fix)
   - Warning (should fix)
   - Suggestion (could improve)

   Include file:line for every finding; do not paste whole files into the report.

## Integration with Other Skills

- **django-models**: model/service/selector boundary (canonical)
- **django-forms**: forms and validation in the UI layer
- **django-templates**, **htmx-patterns**, **htmx-alpine**: HTML rendering and interaction
- **pytest-django-patterns**: testing services, selectors, and views
- **systematic-debugging**: diagnose failed checks or regressions
