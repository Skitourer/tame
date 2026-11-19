# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project skeleton: uv + hatchling packaging (`src/` layout), ruff, mypy, pytest,
  pre-commit and GitHub Actions CI (Windows and Linux).
- `tame` and `tk` commands.
- `tame version` command, showing app and database schema versions.
- Task model and SQLite storage with schema migrations. `tasks.db` lives in `%APPDATA%\tame`
  on Windows, `~/.local/share/tame` elsewhere (XDG), or in `TAME_HOME`.
- `add` command with `project:`, `pri:`/`priority:`, `+tag` and `--`.
- `list` command (also the default when no command is given): pending tasks in a table,
  empty columns hidden.
- Output is always UTF-8, including when redirected.
- Hybrid command line: filter before the command (`tk project:home list`) or after it
  (`tk list project:home`); unique command prefixes (`tk mod`); no command means `list`.
- Filters: ids (`3`, `3,5`, `2-6`), uuid prefixes, `+tag`/`-tag`, `project:`, `pri:`,
  `status:` and description words. See `docs/grammar.md`.
- `done`, `delete` (soft) and `modify` commands. They require a filter and ask for
  confirmation above 3 tasks (`delete`: always); `--yes` skips it. Pending tasks are
  renumbered after `done`/`delete`.
- `info` command: every field of the matching tasks, in local time.
- Due dates: `due:` in `add`/`modify`, `due.before:`/`due.after:` filters. Dates: ISO,
  `today`/`tomorrow`/`yesterday`, weekdays, `eow`/`eom`/`eoy`, offsets (`+3d`, `-1w`...).
- Urgency (priority, due, age, tags, project): `list` sorts by it and shows it (`Urg`),
  `info` shows it. Overdue tasks are red, tasks due today yellow.
- `undo` command: reverts the last `add`, `done`, `delete` or `modify`, ids included;
  repeat it to go further back.
- Settings file `config.toml`, created on first run with commented defaults: `language`,
  `confirm_threshold`, `date_format`, `color`, `undo.retention` (default 3 months) and
  urgency weights. Invalid settings are reported with the key and file.
- `config` command: list, `get`, `set`, `unset`, `path`, `edit`. `set` keeps comments.
- Undo history older than `undo.retention` is purged on each change.
- `help` command: `tk help` lists commands, `tk help <command>` shows usage and
  examples, topics `filters`, `dates`, `urgency`; `tk <command> --help` works too.
- French user interface: `tk config set language fr`. Commands, attributes and date
  keywords stay in English; confirmations also accept `o`/`oui`. Untranslated messages
  fall back to English.
- `status:all` filter: tasks of every status (`tk status:all list`).
- `export` command: matching tasks as Taskwarrior JSON on stdout.
- `import` command: Taskwarrior JSON (array or one object per line) from a file or
  stdin, merged by uuid (newer `modified` wins); unsupported attributes are kept and
  exported back. Reads UTF-16 files written by PowerShell 5. Undoable in one step.
- `alias` command: `tk alias install task` adds an opt-in `task` command (any name but
  `tame`/`tk`) next to `tame` and `tk`; `tk alias remove task` deletes it. Never touches
  files it did not create; warns if the directory is not in PATH or another command of
  that name comes first.
- A few hidden easter eggs.
- First run: `tk` with no task at all shows a welcome with the first commands to try.
- `tk help tour`: a two-minute guided tour.
- README badges (CI, Python, license, ruff, mypy). CI fails under 90 % test coverage
  and shows the coverage report in each run's summary.
- Documentation site (MkDocs Material on GitHub Pages): getting started, commands,
  grammar, urgency, settings, coming from Taskwarrior; coverage and docs badges.
- One-line installers (`install.ps1`, `install.sh`) that install uv if needed, then TAME;
  "Installation for beginners" page.
- CI installs the built package as a uv tool on Windows and Linux and runs a smoke test.
- Release workflow: a `vX.Y.Z` tag builds and checks the package, publishes it to PyPI
  (trusted publishing, after approval) and creates the GitHub release with install notes.

### Changed

- The package is named `tame-tasks` (PyPI); commands stay `tame` and `tk`. The
  installers remove an install made under the old name.
- `status:all list` (and any list mixing statuses) shows pending tasks first.

### Fixed

- `list status:completed` no longer shows `None` in the ID column.
