# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Easter eggs in color**: the hidden extras now have colors of their own, and the same
  blank lines around them as every other output.

## [0.3.4] - 2026-11-20

Output that is easier to read at a glance.

### Added

- **`tk help security`** (and a *Data security* page): your tasks are not encrypted by TAME;
  how to protect them with BitLocker or EFS, and why TAME does not encrypt the file itself.
- **`NO_COLOR`**: set this environment variable to turn colors off, whatever `color` says.

### Changed

- **Clearer output**: in a terminal, each command's output is framed by blank lines, apart
  from your prompt; messages start with `✓` (done), `✗` (error), `!` (warning) or `?`
  (question). Files and pipes still get plain text.
- **`list` and `next`**: one color per column (project, tags, priority, urgency); only the due
  date and id of overdue or due-today tasks are red or yellow, no longer the whole row; a last
  line counts the tasks: `5 tasks · 1 overdue · 1 due today`.
- **`info`**: a `Task 7  <description>` title, then the fields in blocks (task, dates, notes,
  uuid), each date followed by how long ago or how soon (`overdue by 2 days`); no more
  Name/Value header. Scripts should read `tk export` instead.
- **Help**: section labels, commands and examples stand out.

## [0.3.3] - 2026-11-20

Tab completion in both PowerShells, and now in Git Bash.

### Added

- **Tab completion in Git Bash**: on Windows, `tk config set completion true` now also
  sets it up in Git Bash (`~/.bashrc`) when Git for Windows is installed; candidates no longer
  end with a stray `^M` there.

### Fixed

- **Tab completion in both PowerShells**: when TAME was run from PowerShell 7, it missed
  Windows PowerShell's profile (and the reverse could happen), so completion worked in
  only one of them. Run `tk config set completion true` once to set up the other.

## [0.3.2] - 2026-11-20

A face, and help on every setting.

### Added

- **A logo**: a ticked box with a small heart on its corner, on the README, the
  documentation site and its browser tab.
- **Help on settings**: `tk help settings` lists every setting with what it does, its
  possible values and its default; `tk help config date_format` shows one, with its current
  value. In English and French; Tab completes the setting names.

## [0.3.1] - 2026-11-20

Tab completion, now a simple setting.

### Changed

- **Tab completion is a setting**: `tk config set completion true` adds it to your
  PowerShell (or bash) profile and keeps it up to date; `false` removes it. TAME suggests it
  once, the first time it runs in a terminal. Nothing is written when PowerShell does not
  run profile scripts. `tk completion powershell|bash` still prints the script, for other
  setups; it is no longer in the `tk help` list.

### Fixed

- `tk completion` without a shell said *Unknown shell ''*; it now shows its usage and how to
  turn completion on.

## [0.3.0] - 2026-11-20

Everyday comfort, nothing new to learn: plain commands work as before, the new things are
there when you type them.

### Added

- **`tk next`**: the 10 most urgent tasks you can do now, in a compact table; blocked tasks
  are left out. Works with filters: `tk +home next`. `next_limit` sets how many;
  `tk config set default_command next` makes it what `tk` alone shows.
- **Virtual tags**: filter on what TAME computes, without tagging anything yourself.
  `tk +OVERDUE` lists late tasks, `tk +TODAY print` prints today's page, `tk -TAGGED` shows
  tasks without tags. Also `TOMORROW`, `WEEK`, `MONTH`, `DUE` (next 7 days), `BLOCKED`,
  `UNBLOCKED`, `WAITING`, `ANNOTATED` and `PROJECT`. See `tk help filters`; `tk info` lists
  a task's virtual tags.
- **Annotations**: `tk 3 annotate Call back Monday` adds a dated note to a task;
  `tk 3 denotate Call` removes it (or, without text, the most recent one). `tk info` shows
  the notes, `tk print` prints them under the task, and `list`/`next` show how many:
  `Call bank [2]`.
- **`wait:`**: `tk add Chase the bank wait:mon` puts a task aside until a date. It is left
  out of `list`, `next`, `print` and filters until then (a last line says how many are
  hidden), and shows again by itself. `tk +WAITING` lists them; `export` keeps them.
- **Tab completion** in PowerShell and bash: `tk completion powershell >> $PROFILE` once,
  then Tab completes commands, attributes, your tags and projects, date keywords, help
  topics and settings. Not available in cmd.exe.

### Changed

- **Database schema 3**: annotations and dependencies get their own tables; `wait`, and
  `start`, `recur`, `until` for the next version, become real fields. Taskwarrior values
  kept from an import are moved into them. Your database is upgraded automatically the
  first time you run `tk`; nothing to do. An older TAME cannot open it afterwards.
- Taskwarrior import/export: annotations, dependencies, `wait`, `start`, `recur` and `until`
  round-trip natively; `depends` is exported as a list of uuids; `waiting` tasks are
  imported as pending with their `wait` date and exported as `pending` (Taskwarrior 3
  style).
- `tk info` shows annotations, dependencies, `wait`, `start`, `recur` and `until`.
- The virtual tag names (`OVERDUE`, `TODAY`…) are reserved: `add` and `modify` refuse to set
  them. Such tags imported from Taskwarrior are kept, and `modify -NAME` removes them.
- New commands make some short prefixes ambiguous: `tk de` (`delete`, `denotate`), `tk c`
  and `tk co` (`completion`, `config`). Type `del` or `con`.

### Fixed

- A description containing `[...]` is no longer read as color markup in tables.

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
