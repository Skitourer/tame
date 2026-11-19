# TAME

**TAME Arranges My Errands** — a lightweight, Taskwarrior-inspired command-line task manager,
Windows 11 first.

> Status: pre-alpha. `add`, `list` (with filters), `done`, `delete`, `modify`, `info` and
> `version` work, with due dates and urgency; see the
> roadmap in [docs/SPEC.md](docs/SPEC.md#8-layout-quality-release).

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
tk version
```

Filter syntax and parsing rules: [docs/grammar.md](docs/grammar.md).

Tasks are stored in `%APPDATA%\tame\tasks.db` on Windows and `~/.local/share/tame/tasks.db` on
Linux (`$XDG_DATA_HOME` is honored). Set `TAME_HOME` to use another directory.

Planned V1 commands: `add list done delete modify info undo export import help version alias`.
See [docs/SPEC.md](docs/SPEC.md) for the full specification.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
