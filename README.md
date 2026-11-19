# TAME

**TAME Arranges My Errands.** A small, fast to-do list for your terminal: add a task in one
line, see what matters most, tick it off, move on.

```text
> tk add Call the bank +phone due:fri pri:H
Created task 1.
> tk add Water the plants project:home
Created task 2.
> tk
ID   Age   Project   Tags    Pri   Due          Description         Urg
───────────────────────────────────────────────────────────────────────
 1    5s             phone   H     2026-11-20   Call the bank      15.8
 2    3s   home                                 Water the plants    1.0
> tk 1 done
Completed task 1 'Call the bank'.
```

- **Quick to type**: `tk` lists your tasks, `tk 3 done` completes one, commands shorten
  (`tk mod`), and dates speak plain English: `due:fri`, `due:eom`, `due:+2w`.
- **Most urgent first**: priority, due date, age, tags and project add up to an urgency
  score, so the top of the list is what to do now.
- **Forgiving**: `tk undo` reverts any change, bulk changes ask first, deleted tasks are
  kept.
- **Windows first**, at home on Linux too. English or French interface.
- **Taskwarrior-friendly**: same grammar spirit, and its JSON imports and exports both ways.

> Status: pre-alpha, all V1 commands work. See the roadmap in
> [docs/SPEC.md](docs/SPEC.md#8-layout-quality-release).

## Install

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv tool install git+https://github.com/skitourer/tame
```

This installs two commands: `tame` and its short alias `tk`. Then try `tk help`.

## Usage

```sh
tk add Call bank project:home +phone due:fri pri:H  # Created task 1.
tk add -- done the report                    # everything after -- is description
tk list                                      # most urgent first; or just: tk
tk due.before:eow                            # due before the end of the week
tk project:home list                         # filter first (or: tk list project:home)
tk +phone -work bank                         # tags and description words
tk 2-6 pri:H                                 # ids and priority
tk 3,5 done                                  # complete tasks 3 and 5
tk 4 delete                                  # asks first; --yes skips the question
tk 1 modify due:+3d -phone Call the bank     # set, untag, new description
tk 7 info                                    # every field
tk undo                                      # revert the last change (repeat to go back)
tk status:all export > backup.json           # Taskwarrior JSON; status:all = every task
tk import tw.json                            # from Taskwarrior (task export > tw.json)
tk alias install task                        # opt-in: also run tame as `task`
tk help                                      # commands; tk help <command|topic>
tk modify --help                             # same as: tk help modify
tk version
```

Filter syntax and parsing rules: [docs/grammar.md](docs/grammar.md).

Tasks are stored in `%APPDATA%\tame\tasks.db` on Windows and `~/.local/share/tame/tasks.db` on
Linux (`$XDG_DATA_HOME` is honored). Set `TAME_HOME` to use another directory.

## Settings

Settings live in `config.toml`, next to `tasks.db` on Windows (`~/.config/tame` on Linux). It is
created on first run, with every option and a comment. Edit it by hand, or:

```sh
tk config                              # list settings; changed ones show their default
tk config set language fr              # French interface (commands stay in English)
tk config set undo.retention 1y        # keep undo history one year (default 3m; or forever)
tk config set confirm_threshold 5      # ask before changing more than 5 tasks
tk config set date_format %d/%m/%Y
tk config unset date_format            # back to the default
tk config get color
tk config edit                         # open in $EDITOR (Notepad on Windows)
tk config path
```

Other options: `color`, and the urgency weights `urgency.pri_H`, `urgency.due`...

See [docs/SPEC.md](docs/SPEC.md) for the full specification.

## Thanks

TAME exists because [Taskwarrior](https://taskwarrior.org) showed how good a command-line task
manager can be. Many thanks to its team and community for years of great work and for an open
JSON format that lets tools talk to each other.

TAME is an independent project: it shares no code, name or logo with Taskwarrior, and only aims
for compatibility with its JSON import/export format.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
