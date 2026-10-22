<!-- Title must follow Conventional Commits: type(scope): description -->

## Summary

<!-- What changes and why. One paragraph. -->

## Type of change

- [ ] `feat` — new capability
- [ ] `fix` — bug fix
- [ ] `perf` — performance
- [ ] `refactor` — no behavior change
- [ ] `docs` / `test` / `build` / `ci` / `chore`

## Target branch

- [ ] `feature|fix|chore|docs|refactor|test|perf|build|ci/*` -> `develop`
- [ ] `release/*` or `hotfix/*` -> `main`
- [ ] `develop` -> `main`

## Changes

<!-- Bullet list of the meaningful edits. -->

-

## How to test

<!-- Exact steps a reviewer can run. -->

```bash
uv run pytest <path>
```

## Screenshots / recordings

<!-- Required for UI changes (HTMX/Alpine/Tailwind). Before and after. -->

## Checklist

- [ ] Commits follow Conventional Commits and the PR title does too
- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run pyright`
- [ ] `uv run pytest`
- [ ] Tests added or updated for the new behavior
- [ ] Docs/skills updated when conventions changed
- [ ] No secrets, `.env`, or debug prints in the diff
- [ ] Accessibility considered for dynamic UI (focus, ARIA, keyboard)

## Related issues

<!-- Closes #123 -->
