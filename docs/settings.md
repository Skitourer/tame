# Settings

Settings live in `config.toml`:

| OS | File |
|---|---|
| Windows | `%APPDATA%\tame\config.toml` |
| Linux | `~/.config/tame/config.toml` (`$XDG_CONFIG_HOME` honored) |

With `TAME_HOME` set, the file is `$TAME_HOME/config.toml`. `tk config path` prints it.

The file is created on first run with every setting and a comment. A missing setting uses its
default. Edit the file by hand, or use `tk config`, which keeps your comments.

## `tk config`

```text
tk config                              # list settings; changed ones show their default
tk config get undo.retention
tk config set undo.retention 1y
tk config unset undo.retention         # back to the default
tk config path                         # where the file is
tk config edit                         # open it in $VISUAL / $EDITOR (Notepad on Windows)
tk help settings                       # every setting: what it does, values, default
tk help config date_format             # one setting, with its current value
```

Booleans accept `true`/`false`, `yes`/`no`, `on`/`off`, `1`/`0`.

## All settings

| Key | Default | Meaning |
|---|---|---|
| `language` | `"en"` | interface language: `en` or `fr`. Commands, attributes and date keywords stay in English |
| `confirm_threshold` | `3` | `done`, `modify` ask before changing more tasks than this (`delete` always asks) |
| `date_format` | `"%Y-%m-%d"` | how dates are shown ([strftime codes](https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes)), e.g. `%d/%m/%Y` |
| `color` | `true` | colored output in the terminal; the `NO_COLOR` environment variable turns it off too (see [Output](commands.md#output)) |
| `kindness` | `true` | now and then, a kind word about the people around you (see [below](#kind-words)) |
| `default_command` | `"list"` | what `tk` alone (or `tk <filter>`) runs: `list` or [`next`](commands.md#next) |
| `next_limit` | `10` | how many tasks [`next`](commands.md#next) shows (1 or more) |
| `multiple_active` | `false` | `false`: [`tk start`](commands.md#start) stops the task already started; `true`: several can run at once |
| `completion` | `false` | Tab completion in your shell: `true` adds it to your PowerShell (or bash) profile, `false` removes it (see [completion](commands.md#completion)) |
| `undo.retention` | `"3m"` | how long undo history is kept: `forever`, or `<n>d`/`w`/`m`/`y` (m = 30 days, y = 365 days) |
| `urgency.pri_H` | `6.0` | [urgency](urgency.md) weight of priority H |
| `urgency.pri_M` | `3.9` | weight of priority M |
| `urgency.pri_L` | `1.8` | weight of priority L |
| `urgency.due` | `12.0` | weight of the due date |
| `urgency.age` | `2.0` | weight of the age |
| `urgency.tags` | `1.0` | weight of having tags |
| `urgency.project` | `1.0` | weight of having a project |
| `urgency.blocked` | `-5.0` | added when the task waits for another pending task |
| `urgency.blocking` | `8.0` | added when another pending task waits for it |
| `urgency.active` | `4.0` | added while the task is started |

The file looks like this (comments shortened):

```toml
language = "en"
confirm_threshold = 3
date_format = "%Y-%m-%d"
color = true
kindness = true
default_command = "list"
next_limit = 10
multiple_active = false
completion = false

[undo]
retention = "3m"

[urgency]
pri_H = 6.0
due = 12.0
```

## Kind words

Now and then, after a command, TAME adds a short line about what matters more than errands:
friends, family, colleagues, free time, nature, others.

```text
> tk 3 done
Completed task 3 'Water the plants'.

♥ Look up: the sky changes every day, and it's free.
```

They are rare: at most one every three days, then by chance. One also appears when you
complete your last task (a phrase made for that moment), and at the foot of a printed list. They never go into files, pipes
or error messages. Don't want them? `tk config set kindness false`.

## Mistakes in the file

An unknown setting, a wrong type or an invalid value stops every command with a message naming
the setting and the file (exit code 1). `tk config` and `tk help` still work, so you can fix
it: `tk config unset <key>` or `tk config edit`.
