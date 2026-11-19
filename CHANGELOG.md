# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Project

- CI: GitHub Actions moved to their Node.js 24 versions; Dependabot keeps them up to date.
- The Release workflow can be rehearsed by hand (build and check only).

## [0.1.0] - 2026-11-19

First release: a small, fast to-do list for the terminal, Windows first, Taskwarrior-friendly.

### Tasks

- `add`, `list`, `info`, `modify`, `done`, `delete` (kept, with `status:deleted`), `undo`
  (any number of steps back, ids included).
- Attributes: description, project (dotted: `home.garden`), tags, priority H/M/L, due date.
- Dates in plain English: `today`, `tomorrow`, `fri`, `eow`, `eom`, `eoy`, `+3d`, `+2w`,
  or ISO `2026-12-15`.
- Urgency: priority, due date, age, tags and project add up; `list` shows the most urgent
  first (pending tasks first when statuses are mixed). Overdue tasks red, due today yellow.
- Confirmation before bulk changes (`delete` always asks); `--yes` skips it.

### Command line

- Taskwarrior-style grammar: filter before the command (`tk +phone list`) or after it;
  short command prefixes (`tk mod`); `tk` alone lists tasks.
- Filters: ids (`3`, `3,5`, `2-6`), uuid prefixes, `+tag`/`-tag`, `project:`, `pri:`,
  `status:` (including `status:all`), `due.before:`/`due.after:`, description words.

### Taskwarrior

- `export` / `import` in Taskwarrior JSON, merged by uuid; attributes TAME does not use
  (annotations, recurrence, UDAs…) are kept and exported back.
- `tk alias install task`: opt-in `task` command.

### Comfort

- English or French interface (`tk config set language fr`).
- Settings in `config.toml`, managed with `tk config`.
- Help for every command (`tk help`, `tk <command> --help`), topics, and a two-minute
  guided tour (`tk help tour`); a welcome on first run.
- One-line installers for Windows and Linux: no Python needed.
- A few hidden easter eggs.

### Project

- Documentation site: https://skitourer.github.io/tame/
- Published on PyPI as `tame-tasks`; commands `tame` and `tk`.
- CI on Windows and Linux (lint, types, tests with a 90 % coverage gate, install check).
