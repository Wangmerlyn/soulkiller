# Repository Guidelines

## Project Structure & Module Organization

Soulkiller is a Python 3.12 CLI using a `src/` layout. Application code lives in
`src/soulkiller/`: `cli.py` defines commands, `sync.py` coordinates backups,
`scanner.py` guards the generated extra backup repo, and scheduler support is in
`timer.py` and `scheduler.py`. The executable wrapper is `bin/soulkiller`.
Tests are in `tests/` and mirror the main modules, for example
`tests/test_sync.py` and `tests/test_scanner.py`. Design and implementation
notes live under `docs/superpowers/`. Do not add real memory data or backup
snapshots to this repository.

## Build, Test, and Development Commands

- `./bin/soulkiller init-config`: create the default user config at
  `~/.config/soulkiller/config.toml`.
- `./bin/soulkiller status`: print configured Codex memory and extra backup
  paths.
- `./bin/soulkiller sync`: run the local backup workflow.
- `pytest -q`: run the full test suite.
- `python -m soulkiller sync`: run the package entry point when `PYTHONPATH=src`
  is available.

No compile step is required.

## Coding Style & Naming Conventions

Use standard Python style with 4-space indentation, type annotations where they
clarify interfaces, and small functions with explicit return values. Keep module
names lowercase with underscores. Tests should be named `test_<behavior>` and
should exercise public behavior, not implementation details. Prefer stdlib
dependencies unless a new dependency is clearly justified.

## Testing Guidelines

Use pytest. Add or update focused tests for every behavior change, especially
around git operations, scheduling, restore behavior, and safety scanning. Run
`pytest -q` before committing. For CLI behavior, use `bin/soulkiller` in tests or
manual checks so the wrapper path stays covered.

## Commit & Pull Request Guidelines

Follow the existing concise history style: either an imperative subject
(`Scope memory backup safety scanning`) or a scoped prefix such as `feat: ...`,
`fix: ...`, `docs: ...`, or `chore: ...`. Keep commits logically scoped. PRs
should include a short summary, test plan, and any operational notes, such as
scheduler or backup-path changes. For changes that affect backup safety, mention
whether the Codex memories repo, the generated extra backup repo, or both are
affected.

## Security & Configuration Tips

This public repo must stay free of private memory, transcripts, secrets, and
backup snapshots. Codex memories stay in `~/.codex/memories` and are synced as
their own git repo. Soulkiller safety scanning applies to the generated extra
backup repository, not to the Codex memories repo.
