# Getting started

## Install

Never installed a Python program? Follow [Installation for beginners](install-beginners.md).
Otherwise, with [uv](https://docs.astral.sh/uv/):

```sh
uv tool install git+https://github.com/skitourer/tame
```

You get two commands, `tame` and `tk`; they are the same program. This documentation uses
`tk`. To update later: `uv tool upgrade tame`.

## First run

Type `tk`. With no task yet, TAME greets you and suggests a few commands:

```text
> tk
Welcome to TAME! No tasks yet. Try:
  tk add Call the bank due:fri +phone
  tk                 list your tasks, most urgent first
  tk 1 done
Guided tour: tk help tour    Interface en français : tk config set language fr
```

`tk help tour` is a two-minute walk through everything below.

## Add tasks

Words make the description; `project:`, `pri:` (H, M or L), `due:` and `+tag` can go
anywhere:

```sh
tk add Call the bank project:home pri:H due:fri +phone
tk add Buy milk +shopping due:tomorrow
tk add -- done the report       # after --, everything is description
```

Dates are English keywords or ISO dates: `today`, `tomorrow`, `fri`, `eow` (end of week),
`eom`, `+3d`, `+2w`, `2026-12-15`. See [Dates](grammar.md#dates).

## See them

```sh
tk                  # pending tasks, most urgent first (same as: tk list)
tk 1 info           # every field of task 1
```

Overdue tasks are red, tasks due today yellow. The `Urg` column is the
[urgency](urgency.md).

## Change, complete, delete

```sh
tk 2 modify pri:M -shopping     # set, untag
tk 2 modify due:                # clear the due date
tk 1 done                       # complete task 1
tk 3,5 done                     # several at once
tk 4 delete                     # asks first; --yes skips the question
```

After `done` and `delete`, pending tasks are renumbered 1..n.

!!! tip "Made a mistake?"
    `tk undo` reverts the last change, whatever it was. Run it again to go further back.

## Find tasks

A filter goes before the command (or right after it):

```sh
tk +phone                       # tagged phone
tk project:home due.before:eow  # home project, due before the end of the week
tk bank                         # description contains "bank"
tk status:completed list        # completed tasks
```

All filters: [Filters & grammar](grammar.md).

## Make it yours

```sh
tk config set language fr       # French interface
tk config set date_format %d/%m/%Y
tk alias install task           # also run tame as `task`
```

More in [Settings](settings.md). Coming from Taskwarrior? See
[Coming from Taskwarrior](taskwarrior.md).

## Where is my data?

Tasks are in `tasks.db` (SQLite), settings in `config.toml`:

| OS | Folder |
|---|---|
| Windows | `%APPDATA%\tame\` |
| Linux | `~/.local/share/tame/` (tasks), `~/.config/tame/` (settings); XDG variables honored |

Set `TAME_HOME` to keep both somewhere else. Back up with `tk status:all export > backup.json`.
