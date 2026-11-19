# TAME – V1 spec

TAME = *TAME Arranges My Errands*. Lightweight Taskwarrior-like CLI. TW = Taskwarrior.
Repo: github.com/skitourer/tame · License: MIT

## 1. Scope

CLI task manager, Windows 11 first, TW-inspired, simpler. Independent project: no TW code, name or logo reused; TW JSON format compat only.

- **Commands installed**: `tame` (main) + `tk` (short alias, used in examples). `task` = opt-in alias only (`tame alias install|remove task`, shim in uv tools bin dir); never by default (clashes with TW and go-task).
- **In V1**: cmds `add list done delete modify info undo export import help version alias`; attrs description, status, project, tags, priority, due, entry, modified, end; hybrid grammar; EN date keywords; urgency sort; colored table; i18n files; TW JSON import/export.
- **Out V1**: recurrence, depends, annotations, wait, contexts, custom reports, sync, hooks, TUI.
- **Hard rule**: `core` never prints, never reads argv → future TUI reuses it unchanged.

## 2. Stack & standards

| Area | Choice |
|---|---|
| Lang | Python 3.12 baseline (`requires-python >=3.12`, ruff `target-version py312`); no deprecated APIs; full type hints |
| Pkg/env | `uv`; `pyproject.toml` (PEP 621), backend `hatchling`, `src/` layout, `uv.lock` committed |
| Install | `uv tool install git+https://github.com/skitourer/tame` (PyPI later as `tame-tasks`); `[project.scripts] tame = "tame.__main__:main"`, `tk = "tame.__main__:main"` |
| Deps | runtime: `rich`, `python-dateutil` only; stdlib `sqlite3`, `tomllib`; no argparse (custom parser) |
| Lint/format | `ruff check` + `ruff format`, line 100 |
| Types | `mypy --strict` on `src/` |
| Tests | `pytest`, `pytest-cov`, target ≥90% on `core` |
| Hooks | `pre-commit`: ruff, mypy, end-of-file, trailing-ws |
| VCS | GitHub, `main` protected, PRs, Conventional Commits, SemVer, tags `vX.Y.Z` |
| CI | GitHub Actions: lint + types + tests on `windows-latest` and `ubuntu-latest`, Py 3.12 + latest stable |
| Repo files | `README.md`, `CHANGELOG.md` (Keep a Changelog), `CONTRIBUTING.md`, `LICENSE`, `CLAUDE.md`, `docs/`, `.github/` (CI, issue/PR templates) |
| Data dir | Windows: `%APPDATA%\tame\` (`tasks.db`, `config.toml`). Other OS (XDG): `tasks.db` in `$XDG_DATA_HOME/tame/` (default `~/.local/share/tame/`), `config.toml` in `$XDG_CONFIG_HOME/tame/` (default `~/.config/tame/`). Env `TAME_HOME` overrides both and holds both files |
| Output | always UTF-8 on stdout/stderr, also when redirected |
| Perf | lazy-import `rich` in render only; cold start target <250 ms |

## 3. Data model

Field names = TW names. Datetimes stored UTC ISO 8601, shown local.

| Field | Type | Notes |
|---|---|---|
| uuid | str UUIDv4 | PK, permanent |
| id | int | short id, pending only; renumbered (1..n by entry) after done/delete |
| description | str | required |
| status | pending/completed/deleted | delete = soft |
| project | str? | dotted hierarchy `a.b` |
| tags | set[str] | no spaces, no leading `+`/`-` |
| priority | H/M/L? | |
| due, end | datetime? | |
| entry, modified | datetime | auto |

```sql
CREATE TABLE tasks(uuid TEXT PRIMARY KEY, id INTEGER, description TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN('pending','completed','deleted')),
  project TEXT, priority TEXT CHECK(priority IN('H','M','L')),
  due TEXT, entry TEXT NOT NULL, modified TEXT NOT NULL, "end" TEXT,
  extra TEXT); -- JSON: unknown TW attrs kept for round-trip
CREATE TABLE task_tags(uuid TEXT REFERENCES tasks(uuid) ON DELETE CASCADE, tag TEXT, PRIMARY KEY(uuid,tag));
CREATE TABLE undo_log(seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, cmd TEXT NOT NULL, before TEXT NOT NULL); -- JSON snapshot
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT); -- schema_version
```

Each write cmd = 1 transaction + 1 undo_log row. Migrations keyed on `meta.schema_version`.

`before` = `{"tasks": [{uuid, task|null}], "ids"?: {uuid: id}}`: prior state of each changed task (null = created by the cmd, undo removes it); `ids` = pending ids before done/delete renumbering. Cmds that change nothing log nothing. `undo` pops the last row: repeated `undo` goes further back; undo is not itself undoable; empty log → exit 2.

## 4. CLI grammar

```
tk [filter] <cmd> [args]   # TW order (canonical)
tk <cmd> [filter] [args]   # classic order (tolerated)
tk [filter]                # = tk [filter] list (so `tk` = tk list)
```

Parse rules (in order):

1. First token matching a cmd name (exact or unique prefix, e.g. `mod`) = cmd. Cmd names EN only, never translated. A prefix of several cmds → usage error (exit 1), e.g. `d` → delete/done.
2. Tokens before cmd = filter.
3. `add`: all tokens after = new task (mods + description); never a filter.
4. Classic order (nothing before cmd): leading filter-like tokens after cmd (ids, uuid, `+t`, `-t`, `attr:v`) = filter; rest = args. For `modify`, only leading id/uuid tokens are filter. Cmds without args (`list done delete info export`): all tokens after cmd = filter.
5. `--` ends parsing: rest = description words (`tk add -- done the report`); `--` is never a cmd.
6. Unknown `attr:` → usage error (exit 1).
7. Filter given to a cmd that takes none (`add` before it, `alias config help import undo version`) → usage error (exit 1).

Filter tokens (AND-combined, except ids and uuid prefixes which together form one OR-ed selection: `tk 3 5` = tasks 3 and 5; OR/parens out V1; default `status:pending` unless `status:` given):

| Token | Meaning |
|---|---|
| `3` `3,5` `2-6` | ids (digits-only token = always ids) |
| 8+ hex chars | uuid prefix (dashes ignored) |
| `+t` / `-t` | has / lacks tag |
| `project:x` | project = x or x.*; `project:` = no project |
| `pri:H` `status:completed` | equality (`pri` = alias of `priority`); `pri:` = no priority |
| `due.before:fri` `due.after:today` | date compare |
| other word | case-insensitive substring of description |

Mods (`add`, `modify`): `attr:v` set, `attr:` unset, `+t` add tag, `-t` remove tag, other words = description (modify: replaces it).

Bulk: `modify/done/delete` on > `confirm_threshold` (default 3) tasks → y/N prompt; `--yes` skips. `delete` always prompts unless `--yes`.

`modify/done/delete` require a non-empty filter (usage error otherwise). `--yes` is accepted anywhere before `--`, only by these 3 cmds. Answer other than `y`/`yes`, or end of input, = no: nothing changed, exit 0. Messages name tasks by id before renumbering (uuid prefix if no id).

## 5. Commands

| Cmd | Example | Behavior |
|---|---|---|
| add | `tk add Call bank project:home +phone due:tomorrow pri:H` | create; print `Created task <id>.` |
| list | `tk project:home list` | table sorted by urgency desc |
| done | `tk 3,5 done` | status=completed, end=now |
| delete | `tk 4 delete` | status=deleted, end=now |
| modify | `tk 12 modify due:mon -phone` | apply mods |
| info | `tk 7 info` | all fields, local times |
| undo | `tk undo` | revert last write cmd (from undo_log) |
| export | `tk project:home export > f.json` | TW JSON to stdout |
| import | `tk import f.json` | TW JSON; merge by uuid |
| alias | `tk alias install task` | manage opt-in `task` shim |
| config | `tk config set undo.retention 1y` | list / `get` / `set` / `unset` (= default) / `path` / `edit` settings (§7) |
| help | `tk help [cmd\|topic]` | no arg: implemented cmds + 1-line summaries; cmd (exact or prefix): usage, text, examples; topics `filters` `dates` `urgency`. `--help` before `--` = `tk help [<cmd on the line>]`. Works with an invalid config |
| version | `tk version` | app + schema version |

`list` columns: ID Age Project Tags Pri Due Description Urg; hide empty cols; overdue red, due today yellow; `color=false` or non-TTY → plain.

Exit codes: 0 ok, 1 usage error, 2 no match, 3 internal error. Errors → stderr.

## 6. Dates & urgency

Date keywords EN only, any UI language. Date without time → 00:00 local.

| Form | Examples |
|---|---|
| ISO | `2026-12-15`, `2026-12-15T14:00` |
| Day | `today` `tomorrow` `yesterday` |
| Weekday | `monday`..`sunday`, `mon`..`sun` → next occurrence, never today |
| Period end | `eow` `eom` `eoy` → 23:59:59 local of last day (week ends Sunday) |
| Offset | `+3d` `+2w` `+1m` `+4h` `-1d` (from now; `m` = calendar month, day clamped) |

ISO with offset/`Z` and TW `20261215T140000Z` kept as is. Keywords case-insensitive. `due.before:`/`due.after:` are strict; tasks without due never match. Overdue (red) / due today (yellow) = local calendar day of due vs today.

Urgency U = sum, coeffs in config, shown 1 decimal:

- pri: H 6.0, M 3.9, L 1.8
- due: 12 × f; f linear from 0.2 (due ≥14 d ahead) to 1.0 (overdue ≥7 d)
- age: 2 × min(age_days/365, 1)
- tags: 1.0 if any; project: 1.0 if set

## 7. i18n, config, TW compat

**i18n**: all UI text via `t(key, **kw)`; files `src/tame/locales/<lang>.toml`; `en.toml` = reference; missing key → EN fallback. Cmds, attrs, date keywords never translated. Test: every `t()` key in code exists in `en.toml`.

**Config** `config.toml` in the config dir (§2), created on first run with commented defaults; missing keys = default:

```toml
language = "en"
confirm_threshold = 3
date_format = "%Y-%m-%d"
color = true
[undo]
retention = "3m"   # forever | <n>d/w/m/y (m = 30 d, y = 365 d)
[urgency]
pri_H = 6.0
pri_M = 3.9
pri_L = 1.8
due = 12.0
age = 2.0
tags = 1.0
project = 1.0
```

Unknown key, wrong type or invalid value → usage error naming key and file (exit 1); every cmd but `config` stops. Each write cmd purges `undo_log` rows older than `undo.retention`.

`tk config`: no args = list (`key = value`, non-defaults marked); `get KEY`; `set KEY VALUE` (validated; keeps comments, via tomlkit); `unset KEY` (writes the default); `path`; `edit` (`$VISUAL`/`$EDITOR`, else Notepad / vi; file validated after). Keys dotted: `urgency.pri_H`. Bools: true/false/yes/no/on/off/1/0.

**TW JSON**

- Export: JSON array, TW field names, dates `YYYYMMDDTHHMMSSZ`, `extra` keys merged back.
- Import: JSON array or one object per line. Same uuid → update if incoming `modified` newer.
- Unsupported TW attrs (annotations, depends, recur, wait, UDAs…) → stored in `extra`, re-exported unchanged.
- TW status `waiting`/`recurring` → `pending`, original in `extra.tw_status`.

## 8. Layout, quality, release

Layers: `cli` → `core.service` → `storage`. Only `cli.render` imports rich. `core` returns objects / raises typed errors (`TameError` subclasses), never prints.

```
src/tame/
  __main__.py      # main(): parse → dispatch → exit code
  cli/parser.py    # tokens → (filter, cmd, args)
  cli/commands.py  # 1 func per cmd
  cli/render.py    # rich output
  core/models.py   # Task dataclass
  core/filters.py  # Filter (syntax-free)
  core/dates.py    # relative date parser
  core/urgency.py
  core/service.py  # TaskService: add/modify/complete/delete/query/undo
  storage/repo.py  # SQLite repo
  storage/migrations.py
  io/tw_json.py
  i18n.py  config.py  errors.py
  locales/en.toml  fr.toml
tests/             # mirrors src; tmp TAME_HOME fixture
docs/SPEC.md  docs/grammar.md  docs/commands.md
```

**Code docs**: Google-style docstrings on public modules/classes/funcs; parser rules commented with rule numbers from §4.

**Tests**: every example in this spec = a test. Focus: parser, dates (frozen clock), urgency, TW round-trip.

**Release rule** (blocking, every release):

- [ ] README, docs/, `tame help` match current behavior
- [ ] Docstrings up to date on changed code
- [ ] CHANGELOG updated
- [ ] `en.toml` complete; i18n key test green
- [ ] CI green (ruff, mypy, pytest, both OS)
- [ ] Version bumped (SemVer) + git tag + GitHub release

**Roadmap V1** (1 PR each):

1. Repo skeleton, uv, CI, `tame version`
2. Model + SQLite repo + minimal add/list
3. Hybrid parser + filters
4. done/delete/modify/info
5. Dates + urgency
6. undo
7. Config (7a: `config.toml`, `config` cmd, undo purge; 7b: `help`; 7c: i18n FR)
8. TW import/export + `alias`
9. Docs pass → v0.1.0
