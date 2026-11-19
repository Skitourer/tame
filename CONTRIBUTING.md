# Contributing to TAME

The specification in [docs/SPEC.md](docs/SPEC.md) is the source of truth. Read the relevant
section before changing behavior; propose spec changes in the same PR as the code.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/skitourer/tame
cd tame
uv sync
uv run pre-commit install
```

Run the CLI from the checkout with `uv run tame <args>` (or `uv run tk <args>`).

## Checks

All of these must pass before opening a PR (CI runs them on Windows and Linux):

```sh
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest --cov
```

## Conventions

- **Python 3.12** baseline, full type hints, `mypy --strict`.
- **Layers** (SPEC §8): `cli` → `core.service` → `storage`. `core` and `storage` never print,
  never read `argv` and never import `rich`.
- **Docstrings**: Google style on public modules, classes and functions.
- **Tests**: every new behavior gets tests; every example in the spec becomes a test.
- **User-facing text** goes through `t()` with keys in `src/tame/locales/en.toml`
  (once i18n lands).

## Git workflow

- `main` is protected: work on a branch, one roadmap step per branch and PR.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`…).
- Update [CHANGELOG.md](CHANGELOG.md) under `[Unreleased]` for user-visible changes.

## Releases

Versions follow [SemVer](https://semver.org/) and are tagged `vX.Y.Z`. Apply the release checklist
in SPEC §8 before every release.
