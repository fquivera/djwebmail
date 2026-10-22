---
name: conventional-commits
description: Conventional Commits format and rules for this project, including types, scopes, breaking changes, and Commitizen enforcement. Use when writing a commit message, reviewing a PR title, or preparing a release/changelog.
---

# Conventional Commits

Format (spec v1.0.0):

```text
<type>(<scope>)!: <description>

[optional body]

[optional footer(s)]
```

- `type` and `description` are required; `scope` and `!` are optional.
- The description is imperative, lowercase, no trailing period, <= 72 chars.
- Header (type + scope + description) <= 100 chars; aim for <= 72.
- One logical change per commit. If you need "and" in the subject, split it.

## Types

| Type | Use for | Changelog |
|---|---|---|
| `feat` | New user-visible capability | yes (minor) |
| `fix` | Bug fix | yes (patch) |
| `perf` | Performance improvement | yes (patch) |
| `refactor` | Code change, no behavior change | no |
| `docs` | Documentation only | no |
| `test` | Tests only | no |
| `build` | Dependencies, packaging, Docker | no |
| `ci` | CI/CD configuration | no |
| `style` | Formatting only, no logic | no |
| `chore` | Maintenance not covered above | no |
| `revert` | Reverts a previous commit | optional |

Anything that changes public behavior must be `feat` or `fix`, even if the diff
is small. Do not invent types; extend the table in this skill first.

## Scopes

Use the Django app or area touched:

| Scope | Area |
|---|---|
| `accounts` | IMAP/SMTP login and sessions |
| `mail` | Folders, message list, message view |
| `compose` | Compose, reply, forward, send |
| `preferences` | Per-user UI settings |
| `common` | Shared services, templatetags, base templates |
| `config` | Settings, URLs, ASGI/WSGI |
| `deps` | Dependency bumps |
| `ci` | Workflows, hooks, tooling |
| `skills` | `.agents/skills` |
| `release` | Version bumps and changelog |

Omit the scope when the change spans the whole repository or is a tooling-only
change with an obvious type (`ci:`, `docs:`).

## Examples

```text
feat(mail): add HTMX pagination to message list
fix(compose): keep attachments after validation error
perf(mail): prefetch thread messages in one query
docs(readme): document uv setup
build(deps): bump django to 5.2.6
ci: add branch-policy check
test(accounts): cover expired IMAP session
refactor(common): extract toast partial
chore(skills): align Django skills with service boundary
```

Bad:

```text
fixed stuff
Update views.py
feat: Added pagination.
feat(mail): pagination + search + folder tree
FEAT(MAIL): PAGINATION
```

## Body

Explain **why**, not what. The diff already shows what changed.

```text
fix(compose): keep attachments after validation error

The form re-instantiated on POST and dropped the uploaded files,
forcing users to attach them twice. Pass files through the session
until the message is sent.

Refs: #128
```

Wrap at 72 chars. Separate from the header with one blank line.

## Breaking Changes

Two equivalent forms — use both for visibility:

```text
feat(api)!: require authenticated IMAP sessions

BREAKING CHANGE: anonymous folder listing was removed; clients must
authenticate before calling /folders/.
```

`!` before the colon triggers a MAJOR bump; the footer documents migration.
Never ship a breaking change without a migration note in the body or footer.

## Footers

```text
Refs: #42
Closes: #42
Co-authored-by: Name <email>
Reviewed-by: Name <email>
```

Use `Closes:` (or `Fixes:`) so GitHub closes the issue on merge.

## Reverts

```text
revert: feat(mail): add HTMX pagination

This reverts commit 1a2b3c4d5e6f.

Reason: pagination dropped the `q` parameter and broke search.
```

## Atomic Commits

- One concern per commit; tests and implementation may share a commit when the
  test cannot exist meaningfully alone.
- Do not mix formatting, dependency bumps, and behavior changes.
- Commit early and often on feature branches; squash on merge into `develop`.

## Enforcement

Local hook (`.githooks/commit-msg`) validates via Commitizen:

```bash
git config core.hooksPath .githooks   # once per clone
uv run cz commit                      # guided commit message
uv run cz check --rev-range origin/develop..HEAD
```

The hook and CI both use `cz check --commit-msg-file`; passing a file avoids
shell-quoting problems and works across Commitizen 3.x versions.

CI validates the PR title, because `develop` uses **squash merges** and the PR
title becomes the commit subject. Write PR titles in Conventional Commits form.

Merge commits (`Merge branch ...`) are exempt. Everything else must pass.

## Release Coupling

`cz bump` reads commit history to choose the next version and build
`CHANGELOG.md`:

- `fix`/`perf` → PATCH
- `feat` → MINOR
- `!` / `BREAKING CHANGE` → MAJOR (or use `cz bump --increment MAJOR`)

A malformed message therefore corrupts the changelog and the version. Treat the
commit message as part of the release artifact.

## Integration with Other Skills

- **gitflow**: branch types, merge strategy, release and hotfix flow
- **github-actions**: PR title validation and required checks
- **code-quality**: local checks before committing
