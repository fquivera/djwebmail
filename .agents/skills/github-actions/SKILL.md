---
name: github-actions
description: GitHub Actions CI/CD for this Django project, covering workflows, caching, PostgreSQL service, branch policy, commit validation, GHCR images, and releases. Use when editing workflows, debugging a failed check, or releasing a version.
---

# GitHub Actions CI/CD

Two workflows plus repository config:

```text
.github/
├── workflows/
│   ├── ci.yml         # PR + push: lint, types, tests, Django checks, policy
│   └── release.yml    # tag v*.*.*: tests, GHCR image, GitHub Release
├── CODEOWNERS
├── dependabot.yml
└── pull_request_template.md
```

## CI Workflow (`.github/workflows/ci.yml`)

Triggers: `pull_request` into `main`/`develop` and `push` to those branches.

Jobs:

| Job | Name for branch protection | What it does |
|---|---|---|
| `lint` | `lint` | `ruff check`, `ruff format --check`, `pyright` |
| `test` | `test (3.12)`, `test (3.13)` | `pytest` on Python 3.12 + 3.13 with PostgreSQL |
| `django` | `django` | `manage.py check`, `makemigrations --check --dry-run` |
| `branch-policy` | `branch-policy` | validates head/base branch per GitFlow |
| `commit-messages` | `commit-messages` | validates the PR title with Commitizen |

Non-negotiables:

- `permissions: contents: read` at workflow level; elevate per job only.
- `concurrency` cancels superseded runs on the same ref.
- `timeout-minutes` on every job so a hung job cannot burn minutes.
- `fail-fast: false` in the test matrix to see all versions fail.
- Cache via `astral-sh/setup-uv` (`enable-cache: true`).
- Pin actions: `actions/checkout@v7`, `docker/*@v4`+, and `astral-sh/setup-uv`
  at an exact version (`@v10.3.2`) because it does not publish a moving major tag.
- Never echo secrets.

### Bootstrap-safe guards

The repository has no Django code yet. Steps that need code check for it first
and emit a notice instead of failing:

```yaml
- name: Lint
  run: |
    if git ls-files '*.py' | grep -q .; then
      uv run ruff check .
      uv run ruff format --check .
    else
      echo "::notice::No Python files yet; skipping ruff"
    fi

- name: Tests
  run: |
    if git ls-files '*test_*.py' | grep -q .; then
      uv run pytest --cov=apps --cov-report=term-missing
    else
      echo "::notice::No tests yet; skipping pytest"
    fi
```

Remove each guard once the corresponding code exists — a skipped check that
never fails is worse than no check.

### PostgreSQL service

```yaml
services:
  postgres:
    image: postgres:16
    env:
      POSTGRES_USER: djwebmail
      POSTGRES_PASSWORD: djwebmail
      POSTGRES_DB: djwebmail
    ports: ["5432:5432"]
    options: >-
      --health-cmd "pg_isready -U djwebmail"
      --health-interval 5s --health-timeout 5s --health-retries 10
```

Set `DATABASE_URL` in the job `env`. `--reuse-db` from `pyproject.toml` is fine
in CI because the database is ephemeral per job.

### Branch policy job

Encodes GitFlow so a wrong PR target fails before review:

| Head branch | Allowed base |
|---|---|
| `feature/*`, `fix/*`, `chore/*`, `docs/*`, `refactor/*`, `test/*`, `perf/*`, `build/*`, `ci/*` | `develop` |
| `release/*` | `main` |
| `hotfix/*` | `main` |
| `dependabot/*` | `develop` or `main` |
| `develop` | `main` |

### Commit message job

`develop` uses squash merges, so the **PR title** becomes the commit subject.
Write it to a file and validate it (avoids shell-quoting issues and works on
every Commitizen 3.x release):

```yaml
- name: Validate PR title
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  run: |
    printf '%s\n' "$PR_TITLE" > "$RUNNER_TEMP/commit-msg.txt"
    uv run cz check --commit-msg-file "$RUNNER_TEMP/commit-msg.txt"
```

For `push` events validate each non-merge commit in the range, because
Commitizen does not reliably ignore merge commits in `--rev-range`:

```bash
for sha in $(git log --no-merges --format=%H "$BEFORE..$AFTER"); do
  git log -1 --format=%B "$sha" > "$RUNNER_TEMP/commit-msg.txt"
  uv run cz check --commit-msg-file "$RUNNER_TEMP/commit-msg.txt" || exit 1
done
```

## Release Workflow (`.github/workflows/release.yml`)

Trigger: `push` of a tag matching `v*.*.*` (created by `cz bump` / the GitFlow
release flow).

Jobs:

1. `verify` — reuses the CI checks on the tagged commit (never release an
   untested tag).
2. `image` — builds `Dockerfile` and pushes to
   `ghcr.io/<owner>/<repo>:<version>`, `:<major>.<minor>`, and `:latest`.
3. `release` — `gh release create "$TAG" --generate-notes`, marking prereleases
   when the tag contains a hyphen (`v0.3.0-rc.1`).

```yaml
permissions:
  contents: write   # create the release
  packages: write   # push to GHCR
```

Use `docker/login-action` with `${{ github.actor }}` and
`${{ secrets.GITHUB_TOKEN }}`; no extra secret is required for GHCR in the same
repository. Keep `platforms: linux/amd64` unless ARM images are actually needed
(emulation is slow and the image must be tested on that architecture).

## Repository Configuration

- **CODEOWNERS**: `* @fquivera` — every PR requests review.
- **Dependabot**: ecosystems `uv` and `github-actions`, weekly, grouped so one
  PR carries routine bumps; commits must still pass `commit-messages`.
- **Required status checks** on `main` and `develop`: `lint`, `django`,
  `branch-policy`, `commit-messages`, `test (3.12)`, `test (3.13)`.
  A matrix job produces one check per matrix entry — requiring `test` alone
  silently matches nothing.
- **Merge strategy**: allow squash (feature → develop) and merge commits
  (release/hotfix → main). Disable rebase merges to keep history predictable.
- **Secrets**: repository/environment secrets only; never `.env` in the repo.

## Debugging Failing Runs

```bash
gh run list --workflow=ci.yml --limit 10
gh run view <run-id> --log-failed
gh run rerun <run-id> --failed
```

Reproduce locally before pushing:

```bash
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest -x
uv run python manage.py check
```

For workflow syntax, validate with `actionlint` when available. Actions do not
have a local runner by default; prefer reproducing the exact command.

## Anti-Patterns

- No `permissions:` block (defaults to read/write on older repos)
- `pull_request_target` with checkout of untrusted code
- Secrets referenced in `if:` or echo'd in logs
- Fat matrix (every OS × every Python version) with no coverage gain
- Caching `~/.cache/pip` when `uv` is used
- Release workflow that skips tests
- Guards left in place after real code and tests exist
- Third-party actions on moving tags (`@main`) or unpinned commits

## Integration with Other Skills

- **gitflow**: branch names, merge strategy, tag creation
- **conventional-commits**: PR title and commit validation
- **django-infrastructure**: Dockerfile, Gunicorn, settings split
- **code-quality**: the same checks run locally before the PR
- **pytest-django-patterns**: test selection and coverage flags
