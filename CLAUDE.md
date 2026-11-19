# CLAUDE.md

Project: TAME, lightweight Taskwarrior-like CLI (Python 3.12, SQLite, Windows 11 first).
Source of truth: `docs/SPEC.md`. Read the relevant section before coding; do not re-read it all each time.

## Language
- Talk to the user in French.
- Code, comments, docstrings, commits, docs, spec: English.

## Rules
- Follow SPEC §2 standards: uv, src layout, ruff, mypy --strict, pytest, Conventional Commits.
- Respect layers (SPEC §8): `core`/`storage` never print, never read argv, never import rich.
- All user-facing text via `t()`; add keys to `locales/en.toml`.
- Every new behavior gets tests; spec examples become tests.
- One roadmap step = one branch + one PR. Run `uv run ruff check`, `uv run ruff format`, `uv run mypy src`, `uv run pytest` before proposing a commit.
- No author attribution in commit messages or PR descriptions: no `Co-Authored-By`, no "Generated with", no names.
- Spec change needed? Propose it to the user first, then update `docs/SPEC.md` in the same PR.
- Before any release: apply the release checklist (SPEC §8). Docs must match behavior.
- Keep answers short; show diffs, not whole files, unless creating one.
