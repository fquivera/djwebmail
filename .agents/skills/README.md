# Project Skills

Agent skills for DjWebmail. Each directory contains one `SKILL.md`; optional
`references/` files hold detail that is loaded only when needed.

## Conventions

1. **Directory name = `name` in frontmatter.** No version suffixes; put version
   data under `metadata:`.
2. **Frontmatter** must be valid YAML delimited by `---` with `name` and
   `description`. The description states *when* to use the skill and fits in one
   paragraph (<= 1024 chars).
3. **SKILL.md <= 500 lines.** Move depth to `references/` and link it from the
   body. Long reference files get a short table of contents.
4. **No placeholders.** No "create the following files" instructions, bracketed
   filler text, or scaffolds. Files referenced from a skill must exist.
5. **Write in English**, imperative voice, project-standard commands (`uv run ...`).
6. **One owner per topic.** Other skills reference the owner instead of
   restating it. Keep the `## Integration with Other Skills` section at the end.
7. **No unrelated stacks.** This is a Django + HTMX + Alpine project; do not add
   framework references for other languages.

## Topic ownership

| Topic | Owner |
|---|---|
| Model design, QuerySets, model vs service boundary | `django-models` |
| Project layout, services/selectors, DRF, caching, signals, middleware | `django-patterns` |
| Settings split, Docker, requirements, production checklist | `django-infrastructure` |
| Broad Django reference (ORM, DRF, security, deploy, tests) | `django-expert` |
| Forms and validation | `django-forms` |
| Template inheritance, partials, tags | `django-templates` |
| HTMX interaction model, Alpine.js | `htmx-alpine` |
| Django-specific HTMX conventions (CSRF, `HX-Request`, 422) | `htmx-patterns` |
| pytest, factories, TDD | `pytest-django-patterns` |
| Background tasks | `celery-patterns` |
| Management-command introspection | `django-extensions` |
| Lint/type/test audit | `code-quality` |
| Root-cause debugging method | `systematic-debugging` |
| Branching, releases, hotfixes | `gitflow` |
| Commit message format | `conventional-commits` |
| CI/CD workflows and repository config | `github-actions` |
| User-facing text, translations, locales | `i18n` |
| Settings, environment variables, preferences, anti-hardcoding | `configuration` |

Load order for a new feature:

1. `django-patterns` (where the code goes)
2. `django-models` + `django-forms` (domain + input)
3. `django-templates` + `htmx-patterns` + `htmx-alpine` (UI)
4. `i18n` (any user-facing text) + `configuration` (any new setting or literal)
5. `pytest-django-patterns` (tests)
6. `django-infrastructure` (only when touching deploy plumbing)
7. `gitflow` + `conventional-commits` before opening the PR
8. `github-actions` when a CI check fails or a workflow changes
