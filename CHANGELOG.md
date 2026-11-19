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
