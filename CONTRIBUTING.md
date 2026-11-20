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

To try it without touching your real tasks, use the sandbox scripts: they keep tasks,
settings and aliases in `.sandbox/` (ignored by git).

```sh
.\scripts\tk.ps1 add Call bank +phone due:fri   # PowerShell; quote '--'
./scripts/tk.sh add Call bank +phone due:fri    # sh
.\scripts\tk.ps1 --reset                        # start over
```

To check a real install (what CI's `install` job does): build, install as a uv tool in
throwaway directories, then run `python scripts/smoke.py <tool bin dir>`.

Documentation site (MkDocs Material, deployed to GitHub Pages from `main`):

```sh
uv run --group docs mkdocs serve       # preview at http://127.0.0.1:8000
uv run --group docs mkdocs build --strict
```

Shell completion: `completion = true` makes TAME keep a marked block in the shell profile
(`src/tame/cli/shellprofile.py`; tests never touch real profiles, see `tests/conftest.py`).
The scripts printed by `tk completion` call the hidden
`tk _complete _<current word> [words before it...]`, handled in `main()` before anything
heavy is imported. Try it directly: `uv run tk _complete _+` lists your tags.

Easter eggs are hidden in the code and tests (hashed triggers, ROT13 replies). To list
them: `uv run python scripts/spoilers.py` (spoilers!).

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
- **User-facing text** goes through `t()` with keys in `src/tame/locales/en.toml`, the
  reference, translated in `fr.toml` (a test checks both have the same keys and
  placeholders).

## Git workflow

Security issues: do not open a public issue, see [SECURITY.md](SECURITY.md).

- `main` is protected: work on a branch, one roadmap step per branch and PR. Keep PRs
  small and focused; split a large change into several PRs.
- **PRs are squash-merged**: each PR becomes one commit on `main`, titled after the PR.
  Your branch history does not matter ("wip", "fix review" are fine); no need to rebase
  or force-push to tidy it up.
- The **PR title** follows [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`…), e.g.
  `feat: virtual tags`. It becomes the commit message on `main`.
- Co-authors are credited with `Co-authored-by` trailers in the squash commit.
- Avoid branches based on another unmerged branch: after the squash merge, the second
  branch must be rebased onto `main` (`git rebase --onto origin/main <old base>`).
- Update [CHANGELOG.md](CHANGELOG.md) under `[Unreleased]` for user-visible changes.

## Releases

Versions follow [SemVer](https://semver.org/) and are tagged `vX.Y.Z`. Apply the release checklist
in SPEC §8 before every release, then:

1. In a PR: set `__version__` in `src/tame/__init__.py`, rename `[Unreleased]` in the
   CHANGELOG to `[X.Y.Z] - YYYY-MM-DD` (its text becomes the release notes), merge.
2. Tag `main`: `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. The Release workflow builds and smoke-tests the package, then waits: approve the
   `pypi` deployment in the Actions tab. It publishes to PyPI (`tame-tasks`) and creates
   the GitHub release.

To rehearse without publishing: Actions → Release → *Run workflow* runs the build and
check job only (no tag, no PyPI, no GitHub release). Dependabot keeps the GitHub Actions
(pinned by commit SHA, version in a comment) and the Python dependencies up to date, with
one monthly grouped PR each.
