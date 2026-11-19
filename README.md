# TAME

**TAME Arranges My Errands** — a lightweight, Taskwarrior-inspired command-line task manager,
Windows 11 first.

> Status: pre-alpha. All V1 commands work: `add`, `list` (with filters), `done`, `delete`,
> `modify`, `info`, `undo`, `export`, `import`, `alias`, `config`, `help` and `version`, with
> due dates, urgency and a French interface. See the roadmap in [docs/SPEC.md](docs/SPEC.md#8-layout-quality-release).

TAME is an independent project. It shares no code, name or logo with Taskwarrior; it only aims
for compatibility with Taskwarrior's JSON import/export format.

## Install

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv tool install git+https://github.com/skitourer/tame
```

This installs two commands: `tame` and its short alias `tk`.

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

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
