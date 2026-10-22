---
name: gitflow
description: GitFlow branching and release workflow for this repository. Use when creating a branch, choosing a merge strategy, preparing a release or hotfix, tagging a version, or deciding how a change reaches main.
---

# GitFlow Workflow

Classic GitFlow adapted to GitHub protected branches and pull requests.

## Branch Model

| Branch | Purpose | Lifetime | Merges into |
|---|---|---|---|
| `main` | Production. Every commit is a release tag. | permanent | — |
| `develop` | Integration. Always releasable. | permanent | `main` (via release) |
| `feature/<slug>` | New functionality | days | `develop` |
| `fix/<slug>` | Non-urgent bug fix | days | `develop` |
| `chore/*`, `docs/*`, `refactor/*`, `test/*`, `perf/*`, `build/*`, `ci/*` | Maintenance work | days | `develop` |
| `release/<version>` | Stabilize a version, bump version/changelog | hours | `main` **and** `develop` |
| `hotfix/<version>` | Production emergency | hours | `main` **and** `develop` |

Rules:

- `main` and `develop` are protected: no direct pushes.
- Feature branches must branch from `develop` and PR back into `develop`.
- `release/*` and `hotfix/*` branch from `main` and PR into `main`.
- After merging a release or hotfix into `main`, back-merge into `develop`
  (or cherry-pick the tag commit) so history does not diverge.
- Delete the source branch after merge.

## Naming

```text
feature/imap-folder-tree
fix/empty-subject-crash
release/0.2.0
hotfix/0.1.1
docs/skills-gitflow
ci/add-release-workflow
```

- Lowercase kebab-case, ASCII only, no spaces.
- Prefer an issue reference when one exists: `feature/42-imap-folder-tree`.
- Never reuse a branch name after merge.

## Daily Flow

```bash
# Start from an up-to-date develop
git switch develop
git pull --ff-only origin develop
git switch -c feature/42-imap-folder-tree

# Work in small commits (see conventional-commits skill)
git add -p
git commit

# Keep the branch current without rewriting shared history
git fetch origin
git rebase origin/develop        # only if the branch is not shared

# Push and open a PR into develop
git push -u origin feature/42-imap-folder-tree
gh pr create --base develop --fill
```

Merge strategy:

| PR into | Strategy | Why |
|---|---|---|
| `develop` from `feature/*`, `fix/*`, maintenance | **Squash** | One conventional commit per change, clean history, PR title becomes the commit |
| `main` from `release/*`, `hotfix/*` | **Merge commit** (`--no-ff`) | Preserves the release/hotfix boundary and the tag ancestry |
| `develop` from `main` (back-merge) | **Merge commit** | Keeps both histories connected |

Never rebase `main` or `develop`. Never force-push a shared branch.

## Release Flow

Versioning is Semantic Versioning (`MAJOR.MINOR.PATCH`), driven by
Commitizen (`cz bump`) from Conventional Commits.

```bash
# 1. Cut the release branch from main
git switch main && git pull --ff-only origin main
git switch -c release/0.2.0

# 2. Bump version + changelog on the release branch
uv run cz bump --changelog        # updates version, CHANGELOG.md, creates tag locally
git push -u origin release/0.2.0

# 3. PR release/0.2.0 -> main, wait for CI, merge with merge commit
gh pr create --base main --fill

# 4. Tag the merge commit on main (if cz bump did not create it there)
git switch main && git pull --ff-only origin main
git tag -a v0.2.0 -m "v0.2.0"
git push origin v0.2.0            # triggers the release workflow

# 5. Back-merge main -> develop
git switch develop && git pull --ff-only origin develop
git merge --no-ff main
git push origin develop
```

A pushed tag `v*.*.*` runs `.github/workflows/release.yml`: tests, Docker image
to GHCR, and a GitHub Release with generated notes.

## Hotfix Flow

```bash
git switch main && git pull --ff-only origin main
git switch -c hotfix/0.2.1

# Minimal fix + test
git commit -m "fix(mail): avoid crash on empty subject"

uv run cz bump --patch
git push -u origin hotfix/0.2.1
gh pr create --base main --fill

# After merge: tag, release workflow, back-merge into develop
```

If `develop` already contains unrelated changes, cherry-pick the hotfix commit
instead of merging `main` when the merge would drag release-only commits back.

## Protected Branch Settings (GitHub)

Apply to `main` and `develop`:

- Require a pull request (1 approval; 0 while solo but keep PRs mandatory).
- Require status checks: `lint`, `test`, `branch-policy`, `commit-messages`.
- Require branches to be up to date before merging.
- Require conversation resolution.
- Block force pushes and deletions.
- Restrict who can push (nobody for `main`; admins can bypass for emergencies).

## Pre-PR Checklist

- [ ] Branch name follows the table above and targets the right base
- [ ] Commits follow Conventional Commits
- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run pyright`
- [ ] `uv run pytest`
- [ ] No `.env`, secrets, or debug prints in the diff
- [ ] PR template completed and linked issue referenced

## Anti-Patterns

- Committing directly to `main` or `develop`
- Long-lived feature branches (rebase weekly, merge small)
- `release/*` containing new features (only version bump, changelog, fixes)
- Merging a release into `main` without back-merging into `develop`
- Squash-merging `release/*` or `hotfix/*` into `main` (breaks tag ancestry)
- Rewriting history on shared branches
- Tagging a commit that was never tested by CI

## Integration with Other Skills

- **conventional-commits**: commit format, types, breaking changes
- **github-actions**: CI checks, branch-policy job, release workflow
- **code-quality**: pre-PR local checks
- **systematic-debugging**: fix branches should start with a failing test
