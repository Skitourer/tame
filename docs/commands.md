# Commands

Every command, its syntax and examples. `tk help <command>` shows the same in the terminal,
in your interface language. Commands can be shortened to any unique prefix: `tk mod`,
`tk inf`. How a command line is read: [Filters & grammar](grammar.md).

| Command | What it does |
|---|---|
| [`add`](#add) | create a task |
| [`list`](#list) | list tasks, most urgent first (the default command) |
| [`info`](#info) | show every field of tasks |
| [`modify`](#modify) | change tasks |
| [`done`](#done) | mark tasks completed |
| [`delete`](#delete) | delete tasks |
| [`undo`](#undo) | revert the last change |
| [`print`](#print) | print tasks, grouped by project |
| [`export`](#export) | export tasks as Taskwarrior JSON |
| [`import`](#import) | import Taskwarrior JSON |
| [`alias`](#alias) | add or remove a command alias, such as `task` |
| [`config`](#config) | show or change settings |
| [`help`](#help) | show help |
| [`version`](#version) | show the version |

**Exit codes**: 0 success, 1 usage error (bad command line or value), 2 no matching task (or
nothing to undo), 3 internal error. Errors go to stderr.

## add

```text
tk add <description> [project:P] [pri:H|M|L] [due:DATE] [+tag ...]
```

Words make the description; `project:`, `pri:`, `due:` and `+tag` can be anywhere. Everything
after `--` is description, even words like `done` or `+x`. Prints the new task's id.

```sh
tk add Call bank project:home +phone due:fri pri:H
tk add -- done the report
```

## list

```text
tk [filter] list
```

Shows the pending tasks matching the [filter](grammar.md#filter-tokens); `status:completed`,
`status:deleted` or `status:all` shows the others. Pending tasks come first, then everything
is sorted by [urgency](urgency.md), highest first. Empty columns are hidden. Overdue tasks are red, tasks due today yellow (no colors when
the output is not a terminal, or with `color = false`).

`list` is the default command: `tk` alone lists all pending tasks. With no task at all, it
shows a welcome message instead.

```sh
tk
tk project:home             # also: tk list project:home
tk +phone -work bank
tk status:completed list
```

## info

```text
tk [filter] info
```

Shows all fields of the matching tasks, in local time, including the uuid and any attribute
kept from a Taskwarrior import.

```sh
tk 7 info
tk status:deleted info
```

## modify

```text
tk <filter> modify [attr:value] [attr:] [+tag] [-tag] [new description]
```

`attr:value` sets an attribute, `attr:` clears it (`project`, `pri`, `due`); `+tag` and `-tag`
add and remove tags; other words replace the description. A filter is required. Asks before
changing more than `confirm_threshold` tasks (default 3); `--yes` skips the question.

```sh
tk 12 modify due:mon -phone
tk 3 modify project: Call the bank
tk +phone modify pri:L --yes
```

## done

```text
tk <filter> done [--yes]
```

Marks the matching tasks completed. A filter is required. Asks before completing more than
`confirm_threshold` tasks; `--yes` skips it. Pending tasks are then renumbered 1..n.

```sh
tk 3 done
tk 3,5 done
tk +shopping done --yes
```

## delete

```text
tk <filter> delete [--yes]
```

A filter is required. Always asks first; `--yes` skips it. Deleted tasks are kept with
`status:deleted`, and `tk undo` brings them back. Pending tasks are then renumbered 1..n.

```sh
tk 4 delete
tk project:old delete --yes
```

## undo

```text
tk undo
```

Reverts the last `add`, `done`, `delete`, `modify` or `import`, ids included. Run it again to
go further back. History older than `undo.retention` (default 3 months) is purged; see
[Settings](settings.md).

## print

```text
tk [filter] print [--file PATH]
```

Makes a printable page of the matching tasks and opens it in your browser with the print
dialog: pick a printer, or *Save as PDF*. The title shows the filter, with the date and time
printed. One section per project (tasks without a project last), tasks sorted by urgency, each
with a box to tick, its priority (`!H`), tags and due date (`due … · today`, or **late** in
bold). Three empty lines at the end leave room for tasks added by hand, and a
[kind word](settings.md#kind-words) closes the page. Like `list`, only
pending tasks by default. The page follows your interface language and `date_format`.

`--file PATH` saves the page (HTML) without opening it.

```sh
tk print
tk +shopping print
tk project:home due.before:eow print
tk print --file tasks.html
```

## export

```text
tk [filter] export
```

Prints the matching tasks as a JSON array in Taskwarrior format, one task per line; `[]` if
none match. Like `list`, only pending tasks by default: `status:all` exports everything.

```sh
tk status:all export > backup.json
tk project:home export > home.json
```

Format details: [Coming from Taskwarrior](taskwarrior.md#export).

## import

```text
tk import [FILE | -]
```

Reads a JSON array, or one task object per line, from `FILE` or standard input (no `FILE`, or
`-`). UTF-8, or UTF-16 as written by PowerShell 5. Tasks are merged by uuid; the whole import
is one `undo` step. If any task is invalid, nothing is imported and the error names it.

```sh
tk import tw.json
tk status:all export | tk import -
```

Merge rules: [Coming from Taskwarrior](taskwarrior.md#import).

## alias

```text
tk alias install NAME
tk alias remove NAME
```

Creates a small launcher `NAME` (`NAME.cmd` on Windows) running tame, next to the `tame` and
`tk` commands (the uv tool directory, usually `~/.local/bin`). Not done by default: `task` is
also the Taskwarrior and go-task command. Warns if the directory is not in `PATH`, or if
another `NAME` comes first in `PATH`. `remove` deletes only launchers created by tame, and
`install` never overwrites another file.

```sh
tk alias install task
task add Call bank
tk alias remove task
```

## config

```text
tk config [get KEY | set KEY VALUE | unset KEY | path | edit]
```

Without arguments, lists all settings; changed ones show their default. `unset` restores the
default; `edit` opens the file in `$VISUAL`/`$EDITOR` (Notepad on Windows) and checks it
afterwards. Works even when the settings file is invalid, to repair it. All settings:
[Settings](settings.md).

```sh
tk config set language fr
tk config set undo.retention 1y
tk config unset date_format
```

## help

```text
tk help [command | topic]
```

Without arguments, lists commands and topics. Topics: `filters`, `dates`, `urgency`, `tour`
(a two-minute guided tour), `license` (TAME's license and the installed libraries'
licenses) and `credits`. `tk <command> --help` is the same as `tk help <command>`. Works
even when the settings file is invalid.

```sh
tk help modify
tk help tour
tk 3 done --help
```

## version

```text
tk version
```

Shows the tame version and the database schema version, and where to find the license and
credits.
