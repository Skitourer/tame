# Coming from Taskwarrior

TAME is inspired by [Taskwarrior](https://taskwarrior.org) and reads and writes its JSON
format. It is an independent, simpler tool: no code, name or logo is shared.

## Move your tasks over

```sh
task export > tw.json          # in Taskwarrior
tk import tw.json              # in TAME
```

Run the import again later: tasks already there are only updated if they changed in
Taskwarrior since. `tk undo` reverts a whole import.

!!! note "PowerShell 5"
    `>` in Windows PowerShell 5 writes UTF-16 files. TAME reads them as they are.

## Keep typing `task`

```sh
tk alias install task
task add Call bank             # runs TAME
```

This is opt-in on purpose: `task` is Taskwarrior's command (and go-task's). TAME warns if
another `task` comes first in your `PATH`. `tk alias remove task` takes it away.

## What is the same

- The command line: `task 3 done` → `tk 3 done`, `task +phone list` → `tk +phone list`,
  `task 3 modify pri:H` → `tk 3 modify pri:H`. Filter before the command, attributes as
  `name:value`, tags as `+tag`/`-tag`. See [Filters & grammar](grammar.md).
- Attribute names: `description`, `status`, `project`, `tags`, `priority`, `due`, `entry`,
  `modified`, `end`, `uuid`.
- Short ids for pending tasks, renumbered after `done`/`delete`; uuids for the others.
- Urgency-sorted list (with a simpler [formula](urgency.md)).
- Date keywords such as `today`, `fri`, `eom`, `+3d`.

## What is different

- Annotations work as in Taskwarrior (`annotate`, `denotate`). No recurrence, dependency
  commands, `wait`, contexts, custom reports, hooks, sync or UDAs yet. These are kept on
  import and exported back unchanged (see below).
- One status filter value at a time, plus `status:all`. No `or` and no parentheses.
- Priorities are H, M and L only.
- `delete` always asks for confirmation; `tk undo` goes back any number of steps.
- Settings are in a TOML file, `config.toml`, not `.taskrc`. See [Settings](settings.md).

## Export

`tk [filter] export` prints a JSON array with one task per line:

- Taskwarrior field names; dates as `YYYYMMDDTHHMMSSZ` (UTC).
- `id` (0 if the task is not pending) and `urgency` are included for information.
- Attributes kept from an import come back as they were.
- Like `list`, only pending tasks by default: `tk status:all export` exports everything.
- No matching task: `[]`.

## Import

`tk import [FILE | -]` reads a JSON array, or one object per line, from a file or standard
input.

- **Merge by uuid.** A new uuid is added. An existing one is replaced only if the incoming
  `modified` is later; otherwise it is skipped. The summary line counts added, updated and
  skipped tasks.
- **Defaults.** Missing `uuid`: a new one. Missing `entry`: now. Missing `modified`: `entry`.
  Missing `status`: `pending`. `id` and `urgency` are ignored.
- **Annotations and dependencies.** Stored with the task, shown by `tk info` and exported
  back. `depends` is accepted as a list of uuids or as a comma-separated string (older
  Taskwarrior) and is exported as a list.
- **wait, start, recur, until.** Stored with the task and exported back. `wait` works as in
  Taskwarrior; `start`, `recur` and `until` are kept for the features of a later version.
- **Kept for export.** Other unsupported attributes (UDAs…) and a priority other than H/M/L
  are stored with the task and exported back.
- **Statuses.** `waiting` becomes `pending` with its `wait` date, as in Taskwarrior 3; it is
  exported as `pending`. `recurring` becomes `pending`; the original status is restored on
  export while the task is still pending.
- **Ids.** New pending tasks get the next free ids. If the import changes which tasks are
  pending, all pending tasks are renumbered.
- **All or nothing.** If any task is invalid (bad date, empty description…), nothing is
  imported and the error names the task's position in the input.
