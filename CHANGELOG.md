# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`tk next`**: the 10 most urgent tasks you can do now, in a compact table; blocked tasks
  are left out. Works with filters: `tk +home next`. `next_limit` sets how many;
  `tk config set default_command next` makes it what `tk` alone shows.
- **Virtual tags**: filter on what TAME computes, without tagging anything yourself.
  `tk +OVERDUE` lists late tasks, `tk +TODAY print` prints today's page, `tk -TAGGED` shows
  tasks without tags. Also `TOMORROW`, `WEEK`, `MONTH`, `DUE` (next 7 days), `BLOCKED`,
  `UNBLOCKED`, `ANNOTATED` and `PROJECT`. See `tk help filters`. `tk info` lists them.

### Changed

- The virtual tag names (`OVERDUE`, `TODAY`…) are reserved: `add` and `modify` refuse to set
  them. Such tags imported from Taskwarrior are kept, and `modify -NAME` removes them.

- **Database schema 2**: annotations and dependencies imported from Taskwarrior now have
  their own tables, ready for the commands that will use them. Your database is upgraded
  automatically the first time you run `tk`; nothing to do. An older TAME cannot open it
  afterwards.
- `tk info` shows annotations and dependencies.
- `tk export` writes `depends` as a list of uuids, even if it was imported as a
  comma-separated string.

## [0.2.0] - 2026-11-20

A little more paper, and a little more love.

### Added

- **`tk print`**: a printable page of your tasks, one section per project, with a box to
  tick for each, its priority, tags and due date (today, or late in bold), and room to add
  tasks by hand. It opens in your browser with the print dialog: print it, or save it as
  PDF. Works with filters: `tk +shopping print`. `--file PATH` saves the page instead.
- **Kind words**: now and then, a short line about friends, family, colleagues, free time
  and nature (50 phrases, in English and French). At most one every three days, never in
  files or scripts; also when you complete your last task, and at the foot of a printed
  list. `tk config set kindness false` turns them off. And a little secret, for the days
  when you need it.
- **`tk help license`** and **`tk help credits`**: TAME's license, the libraries it uses with
  their licenses, and thanks. `tk version` points to them.

### Project

- GitHub Actions moved to their Node.js 24 versions; Dependabot keeps them up to date.
- The release workflow can be rehearsed by hand.
- Required checks on `main` now include the install test and the docs build.

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
