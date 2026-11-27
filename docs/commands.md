# Commands

Every command, its syntax and examples. `tk help <command>` shows the same in the terminal,
in your interface language. Commands can be shortened to any unique prefix: `tk mod`,
`tk inf`. How a command line is read: [Filters & grammar](grammar.md).

| Command | What it does |
|---|---|
| [`add`](#add) | create a task |
| [`list`](#list) | list tasks, most urgent first (the default command) |
| [`next`](#next) | the most urgent tasks you can do now |
| [`info`](#info) | show every field of tasks |
| [`modify`](#modify) | change tasks |
| [`annotate`](#annotate) | add a dated note to tasks |
| [`denotate`](#denotate) | remove a note from tasks |
| [`start`](#start) | start working on a task |
| [`stop`](#stop) | stop working on tasks |
| [`done`](#done) | mark tasks completed |
| [`delete`](#delete) | delete tasks |
| [`undo`](#undo) | revert the last change |
| [`purge`](#purge) | erase deleted tasks for good |
| [`print`](#print) | print tasks, grouped by project |
| [`export`](#export) | export tasks as Taskwarrior JSON |
| [`import`](#import) | import Taskwarrior JSON |
| [`alias`](#alias) | add or remove a command alias, such as `task` |
| [`completion`](#completion) | Tab completion: how to turn it on (advanced: print the script) |
| [`config`](#config) | show or change settings |
| [`help`](#help) | show help |
| [`version`](#version) | show the version |

**Exit codes**: 0 success, 1 usage error (bad command line or value), 2 no matching task (or
nothing to undo or purge), 3 internal error. Errors go to stderr.

## add

```text
tk add <description> [project:P] [pri:H|M|L] [due:DATE] [wait:DATE] [depends:IDS] [recur:PERIOD] [until:DATE] [+tag ...]
```

Words make the description; `project:`, `pri:`, `due:`, [`wait:`](grammar.md#waiting-tasks),
[`depends:`](grammar.md#dependencies), [`recur:`, `until:`](grammar.md#recurrence) and
`+tag` can be anywhere. Everything
after `--` is description, even words like `done` or `+x`. Prints the new task's id.

```text
tk add Call bank project:home +phone due:fri pri:H
tk add -- +1 vote for the new logo   # after --, +1 is text, not a tag
tk add Chase the bank wait:mon due:fri
tk add Paint the walls depends:2
tk add Backup due:fri recur:weekly until:eoy
```

## list

```text
tk [filter] list
```

Shows the pending tasks matching the [filter](grammar.md#filter-tokens); `status:completed`,
`status:deleted` or `status:all` shows the others. Pending tasks come first, then everything
is sorted by [urgency](urgency.md), highest first. Empty columns are hidden. Each column has
its color (project cyan, tags magenta, priority H red, M yellow, L dim); the due date and id of
overdue tasks are red, of tasks due today yellow. A last line counts the tasks:
`5 tasks · 1 overdue · 1 due today`. See [Output](#output) for when colors show.

`list` is the default command: `tk` alone lists all pending tasks. With no task at all, it
shows a welcome message instead. [Waiting tasks](grammar.md#waiting-tasks) are left out; a
last line says how many (`tk +WAITING` shows them, with a Wait column). To make `next` the
default, see
[`default_command`](settings.md#all-settings).

```text
tk
tk project:home             # also: tk list project:home
tk +phone -work bank
tk status:completed list
```

## next

```text
tk [filter] next
```

Like `list`, for when you wonder what to do now: only the `next_limit` most urgent tasks
(10 by default), without the [blocked](grammar.md#virtual-tags) ones (waiting for another
pending task), and without the Age and Tags columns. If more tasks match, the last lines say
how many: `10 of 34 tasks`, then `tk list shows them all.`

```text
tk next
tk +home next               # also: tk next +home
tk n                        # unique prefix
tk config set default_command next   # then tk alone shows next
```

## info

```text
tk [filter] info
```

Shows all fields of the matching tasks, in local time, under a `Task 7  <description>` title,
in blocks: the task (status, project, tags then [virtual tags](grammar.md#virtual-tags), dim,
priority, urgency...), its dates, each followed by how long ago or how soon
(`overdue by 2 days`, `3 days ago`), its annotations, then its uuid and any attribute kept
from a Taskwarrior import.

```text
tk 7 info
tk status:deleted info
```

## modify

```text
tk <filter> modify [attr:value] [attr:] [+tag] [-tag] [new description]
```

`attr:value` sets an attribute, `attr:` clears it (`project`, `pri`, `due`, `wait`, `recur`, `until`); `+tag` and `-tag`
add and remove tags; other words replace the description. A filter is required. Asks before
changing more than `confirm_threshold` tasks (default 3); `--yes` skips the question.

`depends:3,4` adds tasks 3 and 4 to the ones the task waits for, `depends:-3` removes one,
`depends:` removes them all; see [dependencies](grammar.md#dependencies). `recur:` ends a
[recurring](grammar.md#recurrence) series.

```text
tk 12 modify due:mon -phone
tk 3 modify project: Call the bank
tk +phone modify pri:L --yes
tk 5 modify depends:3,4
```

## annotate

```text
tk <filter> annotate <text>
```

Adds a dated note to each matching task: a follow-up, a phone number, what was said on the
last call. [`info`](#info) shows the notes, [`print`](#print) prints them under the task, and
`list`/`next` show how many a task has, dim, after its description: `Call bank [2]`. A filter
is required; asks before changing more than `confirm_threshold` tasks, `--yes` skips it.
After `--`, words are text even if they look like a command. `tk undo` removes the note.

```text
tk 3 annotate Call back Monday, ask for Ann
tk annotate 3 Call back Monday      # also works: ids right after the command are the filter
tk 3 annotate -- Answer --yes by mail   # after --, --yes is text
tk +ANNOTATED                       # tasks with notes (a virtual tag)
```

## denotate

```text
tk <filter> denotate [text]
```

Removes one note from each matching task: the one with exactly this text (any case), else the
only one containing it, else, without text, the most recent. If several notes contain the
text, nothing is removed and the error lists them: give more of the text. No note removed at
all → exit code 2.

```text
tk 3 denotate Call back
tk 3 denotate                       # the most recent note
```

## start

```text
tk <filter> start [--yes]
```

Marks the task as started (`+ACTIVE`) and counts the time until [`tk stop`](#stop). Started
tasks gain [urgency](urgency.md) (4.0) and the **Active** column of `list` and `next` shows how
long they have been running. `tk info` shows the **Time spent**, all sessions added up.

Only one task runs at a time: starting one stops the other, with its *Stopped…* message. Set
[`multiple_active`](settings.md) to `true` to allow several. `done` and `delete` stop a task
first, keeping its time. Undoable.

```text
tk 3 start
tk +ACTIVE list
```

Exported to Taskwarrior, each session becomes two notes, *Started task* and *Stopped task*,
as Taskwarrior writes them with `journal.time`; importing turns them back into sessions.

## stop

```text
tk [filter] stop
```

Stops the active tasks, all of them or those the filter picks, and records the time spent:
*Stopped task 3 'Write report' after 1h20.* Nothing active: exit code 2.

```text
tk stop
tk 3 stop
```

## done

```text
tk <filter> done [--yes]
```

Marks the matching tasks completed. A filter is required. Asks before completing more than
`confirm_threshold` tasks; `--yes` skips it. Pending tasks are then renumbered 1..n.
A [recurring](grammar.md#recurrence) task comes back as a new task, due one period later:
*Next: task 4 'Backup', due 2026-12-04.*

```text
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
[`tk purge`](#purge) erases deleted tasks for good.

```text
tk 4 delete
tk project:old delete --yes
```

## undo

```text
tk undo
```

Reverts the last `add`, `done`, `delete`, `modify`, `annotate`, `denotate`, `start`, `stop` or `import`, ids included. Run it again to
go further back. History older than `undo.retention` (default 3 months) is purged; see
[Settings](settings.md). [`tk purge`](#purge) clears the whole history.

## purge

```text
tk [filter] purge [--yes]
tk purge --all
```

Erases deleted tasks (`status:deleted`) for good, with their notes and the links other tasks
have to them. A filter picks some of them (`project:old`, a uuid); without one, every deleted
task goes. Always asks first; `--yes` skips it. Another `status:` in the filter is an error.

`--all` erases every task, whatever its status: after the *y/N* question, type the word
`purge` to confirm, in any interface language. `--yes` never skips this step, and it needs a
terminal (from a script or a pipe: usage error). `--all` takes no filter.

Before any purge, a copy of the database is saved next to it, as
`tame-YYYYMMDD-HHMMSS.db.bak` (local time), and its path is shown: copy it back over
`tasks.db` to recover. TAME never removes these copies. A purge cannot be undone: it clears the
`tk undo` history. Nothing to purge: exit code 2, no question, no copy.

Type the full name: `purge` is never reached by a prefix, so `tk p` is still `print`.

```text
tk purge
tk project:old purge --yes
tk purge --all
```

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

```text
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
Waiting tasks are always included.

```text
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
Taskwarrior recurring series are converted: see [Coming from Taskwarrior](taskwarrior.md#import).

```text
tk import tw.json
tk status:all export | tk import -
```

Merge rules: [Coming from Taskwarrior](taskwarrior.md#import).

## completion

**Tab completion** makes Tab complete commands, attributes, your tags and projects, date
keywords and help topics. Turn it on once:

```text
tk config set completion true
```

TAME adds a block to your PowerShell profile (`$PROFILE`), to `~/.bashrc` for Git Bash if
it is installed, and on Linux to `~/.bashrc` if bash is your shell. It keeps the block up
to date; open a new terminal to use it. Then try `tk mo` <kbd>Tab</kbd>, `tk +`
<kbd>Tab</kbd>, `tk project:` <kbd>Tab</kbd> or `tk add x due:` <kbd>Tab</kbd>.
`tk config set completion false` removes the block; the rest of your profile is never
touched. The first time you run TAME in a terminal, it reminds you of this once.

If PowerShell does not run profile scripts on your computer (execution policy `Restricted`),
TAME writes nothing and tells you; `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
allows them, when your organization permits it. The classic Command Prompt (cmd.exe) has no
completion.

For other setups (another shell or profile, your own dotfiles), the advanced command prints
the script, to put where you want:

```text
tk completion powershell | bash
```

```powershell
tk completion powershell | Out-String | Invoke-Expression   # in $PROFILE: always current, slower start
```

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

```text
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

```text
tk config set language fr
tk config set undo.retention 1y
tk config unset date_format
```

## help

```text
tk help [command | topic]
tk help config KEY
```

Without arguments, lists commands and topics. Topics: `filters`, `dates`, `urgency`,
`security` (how to protect your tasks, see [Data security](security.md)), `settings` (every setting: what it does, its values and default), `tour` (a two-minute
guided tour), `license` (TAME's license and the installed libraries'
licenses) and `credits`. `tk <command> --help` is the same as `tk help <command>`. Works
even when the settings file is invalid.

```text
tk help modify
tk help tour
tk help settings
tk help config date_format    # one setting, with its current value
tk 3 done --help
```

## version

```text
tk version
```

Shows the tame version and the database schema version, and where to find the license and
credits.

## Output

In a terminal, every command's output starts and ends with a blank line, so it stands apart
from your prompt, and messages start with a symbol: `✓` done, `✗` error, `!` warning, `?`
question. Colors show only in a terminal, with the [`color`](settings.md#all-settings) setting
on and the `NO_COLOR` environment variable unset or empty. In files and pipes the text is plain,
without blank lines or symbols; `export`, `completion <shell>`, `config get` and `config path`
always print plain data.
