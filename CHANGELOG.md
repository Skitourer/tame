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

### Fixed

- `list status:completed` no longer shows `None` in the ID column.
