# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Template baseline.** Extend this file with project-specific sections
> (project overview, commands, architecture, key files, etc.) — do not
> replace it. The Tool Execution, Git Hooks, and Git Workflow sections
> below encode engineering standards that should remain consistent across
> repositories.

## Tool Execution

Python is managed by [uv](https://docs.astral.sh/uv/). Run scripts with
`uv run python path/to/script.py` or inside an activated venv
(`source .venv/bin/activate`). The interpreter version is pinned in
`.python-version`; dependencies and metadata live in `pyproject.toml`.
Run `uv sync` after a fresh clone to create `.venv/`.

`lefthook` is a globally-installed tool and is invoked directly (no wrapper).

## Git Hooks (Lefthook)

Git hooks are managed by [Lefthook](https://github.com/evilmartians/lefthook).
Install it once globally — via `go install github.com/evilmartians/lefthook@latest`,
`npm install -g lefthook`, or a prebuilt binary from the
[releases page](https://github.com/evilmartians/lefthook/releases) — and run
`lefthook install` from the repo root to register hooks. Configuration lives
in `lefthook.yml`.

**Hooks enforced:**

| Hook | Check | What it blocks |
|------|-------|----------------|
| pre-commit | no-secrets | Plaintext password/token/secret patterns |
| pre-commit | branch-check | Direct commits to `main` |
| commit-msg | conventional-commit | Non-conventional commit message format |
| pre-push | branch-check | Direct pushes to `main` |

Add project-specific pre-push checks (test suites, integration tests, build
verification) by editing `lefthook.yml`. A commented placeholder is included.

**Manual hook execution:**

```bash
lefthook run pre-commit    # Run pre-commit hooks
lefthook run pre-push      # Run pre-push hooks
```

## Git Workflow & Best Practices

When committing changes or managing git for this repository, adhere to the following:

1. **Feature Branches:** Always create a feature branch before making changes.
   Direct commits and pushes to `main` are blocked by Lefthook hooks.
2. **Conventional Commits:** Use standard prefixes: `feat:`, `fix:`, `docs:`,
   `chore:`, `refactor:`, `test:`, `ci:`, `style:`, `perf:`, `build:`, `revert:`.
   Include scopes where applicable (e.g., `feat(auth):`, `fix(api):`). Enforced
   by the commit-msg hook.
3. **Secret Safety:** NEVER commit plaintext credentials. Enforced by the
   pre-commit `no-secrets` hook. Keep secrets in `.env*` (gitignored) or an
   encrypted store; use templated placeholder files for anything that must be
   checked in.
4. **Atomic Commits:** Keep commits logically separated. Don't bundle unrelated
   changes (e.g., feature work, doc sweeps, and formatting refactors should be
   three commits).
5. **Pre-Commit Checks:** Automated via Lefthook (no-secrets, branch-check).
   Manual: `lefthook run pre-commit`.
6. **Clean History:** Prefer `git pull --rebase` when resolving divergent
   branches to keep a linear history.
