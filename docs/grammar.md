# Command-line grammar

Reference for how `tame`/`tk` reads its arguments. Normative source: [SPEC §4](SPEC.md#4-cli-grammar).

```text
tk [filter] <cmd> [args]   # TW order (canonical)
tk <cmd> [filter] [args]   # classic order (tolerated)
tk [filter]                # = tk [filter] list
```

## Finding the command

1. The first token that names a command is the command: the exact name, or a prefix of exactly
   one command (`mod` → `modify`, `l` → `list`). A prefix of several commands is an error
   (`d` → *Ambiguous command 'd': delete, done*). Command names are English only.
2. Tokens before the command are the filter.
3. `add`: every token after it describes the new task; it never takes a filter.
4. Classic order (nothing before the command): the leading filter-like tokens after the command
   are the filter (ids, uuids, `+tag`, `-tag`, `attr:value`), the rest are arguments. For
   `modify`, only leading ids/uuids are the filter.
   Commands without arguments (`list`, `done`, `delete`, `info`, `export`, `print`) treat all
   their tokens as filter, so `tk list +phone bank` works (`print` first takes out its
   `--file PATH` option).
5. `--` stops parsing: it is never a command, and everything after it is plain words
   (`tk add -- done the report`). Before it, `--help` turns the line into
   `tk help <command>` (`tk 3 done --help`), or `tk help` if there is no command.
6. An unknown `attr:` is an error (exit code 1).
7. Commands that take no filter (`add`, `alias`, `config`, `help`, `import`, `undo`, `version`)
   reject one
   (exit code 1).

If no token names a command, the command is `list`: `tk`, `tk +phone`, `tk bank`.

## Modifications (`add`, `modify`)

| Token | Effect |
|---|---|
| `project:home` `pri:H` `due:fri` | set the attribute |
| `project:` `pri:` `due:` | clear it (`modify` only) |
| `+tag` | add the tag (not a [virtual tag](#virtual-tags)) |
| `-tag` | remove the tag (`modify` only; for `add` it is a plain word) |
| other words | the description (`modify`: replaces it) |

After `--`, everything is description. `modify` without any modification is an error.

## Dates

Keywords are English only and case-insensitive. A date without a time means 00:00 local.

| Form | Examples | Meaning |
|---|---|---|
| ISO | `2026-12-15` `2026-12-15T14:00` | local time, unless it has an offset (`Z`, `+01:00`) |
| Day | `today` `tomorrow` `yesterday` | 00:00 local |
| Weekday | `monday`..`sunday`, `mon`..`sun` | next occurrence, never today |
| Period end | `eow` `eom` `eoy` | last second of the week (Sunday), month, year |
| Offset | `+3d` `+2w` `+1m` `+4h` `-1d` | from now; `m` = calendar months |

## Confirmation

`done`, `delete` and `modify` need a filter (`tk done` alone is an error). They ask
*y/N* before changing more than 3 tasks; `delete` always asks. `--yes` (anywhere before
`--`) skips the question. Any answer but `y`/`yes` (or `o`/`oui` with the French interface), or no input at all
(scripts), means no.

After `done` and `delete`, pending tasks are renumbered 1..n by creation time.

## Filter tokens

All criteria are AND-combined. Without `status:`, only pending tasks match; `status:all`
matches every status.

| Token | Matches |
|---|---|
| `3` `3,5` `2-6` `1,4-6` | tasks with these short ids |
| `1a2b3c4d`, `1a2b3c4d-5e6f` | tasks whose uuid starts with this (8+ hex chars; dashes ignored) |
| `+tag` / `-tag` | tasks having / lacking the tag, or a [virtual tag](#virtual-tags) |
| `project:home` | project `home` and its sub-projects (`home.garden`), not `homework` |
| `project:` | tasks without a project |
| `pri:H` (`priority:`) | exact priority; `pri:` = no priority |
| `status:completed` | `pending`, `completed`, `deleted`, or `all` |
| `due.before:fri` `due.after:today` | due strictly before / after the date; tasks without due never match |
| any other word | case-insensitive substring of the description |

Ids and uuid prefixes together form one selection: `tk 3 1a2b3c4d list` shows task 3 *and*
the task with that uuid. A token of digits only is always an id.

## Virtual tags

TAME computes these tags from the other fields; you never set them. Use them like tags in
filters: `+NAME` keeps the tasks that have it, `-NAME` the tasks that do not. They are
uppercase and English, whatever the interface language.

| Tag | Tasks that… |
|---|---|
| `OVERDUE` | are past their due date |
| `TODAY` / `TOMORROW` | are due today / tomorrow |
| `WEEK` / `MONTH` | are due this week (Monday to Sunday) / this month, earlier days included |
| `DUE` | are due in the next 7 days |
| `BLOCKED` / `UNBLOCKED` | depend / do not depend on another pending task |
| `ANNOTATED` | have an annotation |
| `PROJECT` / `TAGGED` | have a project / at least one tag |

The first eight only apply to pending tasks: a completed task is never `OVERDUE`. Days,
weeks and months follow your local calendar. `tk info` lists the virtual tags of a task.

These names are reserved: `tk add x +TODAY` is refused. A real tag with one of these names,
imported from Taskwarrior, is kept and exported back; `tk 3 modify -TODAY` removes it.

```sh
tk +OVERDUE                 # late tasks
tk +TODAY print             # today's page
tk +WEEK -BLOCKED           # due this week, and nothing to wait for
tk project:home -TAGGED     # home tasks with no tag at all
```

## Examples

```sh
tk project:home list        # = tk list project:home = tk project:home
tk +phone -work             # pending tasks tagged phone, not tagged work
tk 2-6 pri:H                # ids 2..6 with priority H
tk bank                     # description contains "bank"
tk status:completed list    # completed tasks
tk status:all list          # every task, whatever its status
```
