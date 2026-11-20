# TAME – V1 spec

TAME = *TAME Arranges My Errands*. Lightweight Taskwarrior-like CLI. TW = Taskwarrior.
Repo: github.com/skitourer/tame · License: MIT

## 1. Scope

CLI task manager, Windows 11 first, TW-inspired, simpler. Independent project: no TW code, name or logo reused; TW JSON format compat only.

- **Commands installed**: `tame` (main) + `tk` (short alias, used in examples). `task` = opt-in alias only (`tame alias install|remove task`, shim in uv tools bin dir); never by default (clashes with TW and go-task). Any name `[A-Za-z0-9][A-Za-z0-9_-]*` but `tame`/`tk` works the same way.
- **In V1**: cmds `add list done delete modify info undo export import help version alias`; attrs description, status, project, tags, priority, due, entry, modified, end; hybrid grammar; EN date keywords; urgency sort; colored table; i18n files; TW JSON import/export.
- **Since 0.2.0**: `print`; help topics `license` and `credits`; kind words (§5).
- **Since 0.3.0**: schema 3, annotations, depends, wait, start, recur, until stored natively (§3); virtual tags (§4); `next` report and `default_command` setting (§5, §7); `annotate`/`denotate` (§5); `wait:` (§4), schema 3; shell completion (§5). **Since 0.3.1**: `completion` setting (§7).
- **Not yet** (see `docs/ROADMAP.md`): dependency commands, recurrence, start/stop, advanced filters (0.4); contexts, custom reports, `--json`, UDAs, hooks, stats (0.5); sync, TUI.
- **Hard rule**: `core` never prints, never reads argv → future TUI reuses it unchanged.

## 2. Stack & standards

| Area | Choice |
|---|---|
| Lang | Python 3.12 baseline (`requires-python >=3.12`, ruff `target-version py312`); no deprecated APIs; full type hints |
| Pkg/env | `uv`; `pyproject.toml` (PEP 621), backend `hatchling`, `src/` layout, `uv.lock` committed |
| Install | `uv tool install tame-tasks` (PyPI; also `git+https://github.com/skitourer/tame`; published by `release.yml` on a `vX.Y.Z` tag via trusted publishing, after approval in the `pypi` environment); one-line installers `install.ps1`/`install.sh` on the docs site install uv if missing, then TAME; `[project.scripts] tame = "tame.__main__:main"`, `tk = "tame.__main__:main"` |
| Deps | runtime: `rich`, `python-dateutil` only; stdlib `sqlite3`, `tomllib`; no argparse (custom parser) |
| Lint/format | `ruff check` + `ruff format`, line 100 |
| Types | `mypy --strict` on `src/` |
| Tests | `pytest`, `pytest-cov`; coverage ≥90% enforced (`fail_under`), report in the CI run summary; badge published with the docs site, no third-party service |
| Hooks | `pre-commit`: ruff, mypy, end-of-file, trailing-ws |
| VCS | GitHub, `main` protected, PRs, Conventional Commits, SemVer, tags `vX.Y.Z` |
| CI | GitHub Actions: lint + types + tests on `windows-latest` and `ubuntu-latest`, Py 3.12 + latest stable; built wheel installed as a uv tool and smoke-tested (`scripts/smoke.py`) on both OS |
| Docs site | MkDocs Material (`docs` dependency group), built `--strict` on every PR, deployed to GitHub Pages from `main` with the coverage badge |
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
| annotations | list[{entry, description}] | timestamped notes, sorted by entry; duplicates allowed (schema v2) |
| depends | set[uuid] | tasks this one waits for; never itself; target may be absent (schema v2) |
| wait | datetime? | hidden until then (§4 Waiting tasks) (schema v3) |
| start, until | datetime? | stored and round-tripped; used from 0.4 (start/stop, recurrence) (schema v3) |
| recur | str? | TW recurrence period, stored as is; used from 0.4 (schema v3) |

```sql
CREATE TABLE tasks(uuid TEXT PRIMARY KEY, id INTEGER, description TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN('pending','completed','deleted')),
  project TEXT, priority TEXT CHECK(priority IN('H','M','L')),
  due TEXT, entry TEXT NOT NULL, modified TEXT NOT NULL, "end" TEXT,
  extra TEXT); -- JSON: unknown TW attrs kept for round-trip
CREATE TABLE task_tags(uuid TEXT REFERENCES tasks(uuid) ON DELETE CASCADE, tag TEXT, PRIMARY KEY(uuid,tag));
CREATE TABLE undo_log(seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, cmd TEXT NOT NULL, before TEXT NOT NULL); -- JSON snapshot
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT); -- schema_version
-- schema v2
CREATE TABLE annotations(id INTEGER PRIMARY KEY, uuid TEXT NOT NULL REFERENCES tasks(uuid) ON DELETE CASCADE,
  entry TEXT NOT NULL, description TEXT NOT NULL);
CREATE INDEX idx_annotations_uuid ON annotations(uuid);
CREATE TABLE depends(uuid TEXT NOT NULL REFERENCES tasks(uuid) ON DELETE CASCADE, depends_on TEXT NOT NULL,
  PRIMARY KEY(uuid, depends_on), CHECK(uuid <> depends_on)); -- depends_on: no FK, target may be absent
-- schema v3
ALTER TABLE tasks ADD COLUMN wait TEXT;   -- also start, recur, "until"
```

Each write cmd = 1 transaction + 1 undo_log row. Migrations keyed on `meta.schema_version`: on open, each missing version is applied in its own transaction (all or nothing); a database newer than the code → `error.db_too_new`, nothing changed.

Migration 1 → 2 (0.3.0): creates `annotations` and `depends`, then moves each task's `extra.annotations` / `extra.depends` into them using the TW import rules (§7) and removes the key from `extra`. A key with any invalid item stays in `extra` unchanged. `undo_log` rows are not rewritten.

Migration 2 → 3 (0.3.0): adds `wait`, `start`, `recur`, `until` to `tasks`, then moves valid `extra.wait`/`start`/`until` (TW dates) and `extra.recur` (string) into them (TW import rules, §7); `extra.tw_status = "waiting"` is dropped once `wait` is set. 0.4 needs no further schema change.

`before` = `{"tasks": [{uuid, task|null}], "ids"?: {uuid: id}}`: prior state of each changed task (null = created by the cmd, undo removes it); `ids` = pending ids before done/delete renumbering. `task` includes `annotations`, `depends`, `wait`, `start`, `recur`, `until`; a snapshot written before schema v3 lacks some of them and has them in `extra` and is read with the TW import rules (§7). Cmds that change nothing log nothing. `undo` pops the last row: repeated `undo` goes further back; undo is not itself undoable; empty log → exit 2.

## 4. CLI grammar

```
tk [filter] <cmd> [args]   # TW order (canonical)
tk <cmd> [filter] [args]   # classic order (tolerated)
tk [filter]                # = tk [filter] list (so `tk` = tk list), or `next` (default_command, §7)
```

Parse rules (in order):

1. First token matching a cmd name (exact or unique prefix, e.g. `mod`) = cmd. Cmd names EN only, never translated. A prefix of several cmds → usage error (exit 1), e.g. `d` → delete/denotate/done.
2. Tokens before cmd = filter.
3. `add`: all tokens after = new task (mods + description); never a filter.
4. Classic order (nothing before cmd): leading filter-like tokens after cmd (ids, uuid, `+t`, `-t`, `attr:v`) = filter; rest = args. For `modify`, `annotate` and `denotate`, only leading id/uuid tokens are filter. Cmds without args (`list next done delete info export print`): all tokens after cmd = filter (`print` first takes out `--file PATH`).
5. `--` ends parsing: rest = description words (`tk add -- done the report`); `--` is never a cmd.
6. Unknown `attr:` → usage error (exit 1).
7. Filter given to a cmd that takes none (`add` before it, `alias completion config help import undo version`) → usage error (exit 1).

Filter tokens (AND-combined, except ids and uuid prefixes which together form one OR-ed selection: `tk 3 5` = tasks 3 and 5; OR/parens out V1; default `status:pending` unless `status:` given; `status:all` = any status):

| Token | Meaning |
|---|---|
| `3` `3,5` `2-6` | ids (digits-only token = always ids) |
| 8+ hex chars | uuid prefix (dashes ignored) |
| `+t` / `-t` | has / lacks tag (virtual tag if `t` is one, see below) |
| `project:x` | project = x or x.*; `project:` = no project |
| `pri:H` `status:completed` | equality (`pri` = alias of `priority`); `pri:` = no priority; `status:all` = any status |
| `due.before:fri` `due.after:today` | date compare |
| other word | case-insensitive substring of description |

**Virtual tags** (since 0.3.0): computed when filtering, never stored. Uppercase, exact case, EN only. Used like tags in filters: `tk +OVERDUE`, `tk +home -TAGGED`. Days, weeks (Monday to Sunday) and months are local calendar periods; `now` = current time.

| Tag | True when |
|---|---|
| `OVERDUE` | pending, due < now |
| `TODAY` / `TOMORROW` | pending, due on the local day today / tomorrow |
| `WEEK` / `MONTH` | pending, due in the current local week / month (earlier days of it included) |
| `DUE` | pending, now ≤ due < now + 7 days |
| `BLOCKED` | pending, depends on at least one pending task |
| `UNBLOCKED` | pending, not `BLOCKED` |
| `WAITING` | pending, wait > now |
| `ANNOTATED` | has at least one annotation |
| `PROJECT` | has a project |
| `TAGGED` | has at least one (real) tag |

Names are reserved: `+NAME` in `add`/`modify` → validation error (exit 1); `-NAME` in `modify` removes a stored real tag of that name. Imported real tags with these names are kept and exported unchanged; in filters the name always means the virtual tag. `WAITING` since `wait:` (0.3.0). Planned: `ACTIVE` (with `start`, 0.4) joins the list and becomes reserved; until then it is an ordinary tag.

Mods (`add`, `modify`): `attr:v` set, `attr:` unset, `+t` add tag, `-t` remove tag, other words = description (modify: replaces it). Attrs: `project`, `pri`, `due`, `wait` (dates as `due`).

**Waiting tasks** (since 0.3.0): a pending task with `wait` > now is *waiting*. Every filter result leaves waiting tasks out, unless the filter has ids/uuids, `+WAITING` or `status:all`; `export` always includes them. Nothing is stored when the date passes: the task simply shows again (its `wait` stays, shown by `info`). Waiting tasks keep their id and urgency. `wait` in the past or after `due` is accepted.

Bulk: `modify/done/delete/annotate/denotate` on > `confirm_threshold` (default 3) tasks → y/N prompt; `--yes` skips. `delete` always prompts unless `--yes`.

`modify/done/delete/annotate/denotate` require a non-empty filter (usage error otherwise). `--yes` is accepted anywhere before `--`, only by these 5 cmds. Answer other than `y`/`yes` (or the UI language's yes words, `confirm.yes`), or end of input, = no: nothing changed, exit 0. Messages name tasks by id before renumbering (uuid prefix if no id).

## 5. Commands

| Cmd | Example | Behavior |
|---|---|---|
| add | `tk add Call bank project:home +phone due:tomorrow pri:H` | create; print `Created task <id>.` |
| list | `tk project:home list` | table, pending tasks first, then by urgency desc; an annotated task's description ends with its annotation count, dim: `Call bank [2]`; a Wait column after Due (hidden when empty); if waiting tasks were left out, a last line `N waiting task(s) hidden: tk +WAITING shows them.`; no filter and no task at all (any status) → welcome with first commands, exit 0 |
| next | `tk next`, `tk +home next` | `list` limited to what can be done now: the tasks matching the filter (pending by default) minus `+BLOCKED` ones, same sort and colors, first `next_limit` (default 10) only; columns ID, Project, Pri, Due, Description, Urg (empty ones hidden; annotation count, Wait column and hidden-waiting line as for `list`); if more tasks match, a last line `N of M tasks. tk list shows them all.`; no match → exit 2 (or the welcome message, like `list`). Since 0.3.0 |
| done | `tk 3,5 done` | status=completed, end=now |
| delete | `tk 4 delete` | status=deleted, end=now |
| modify | `tk 12 modify due:mon -phone` | apply mods |
| annotate | `tk 3 annotate Call back Monday` | add an annotation (entry = now) to each matching task; text = all args (`--` dropped, rest kept); empty text → usage error; `modified` = now; undoable; print `Annotated task <id> '<description>'.` Since 0.3.0 |
| denotate | `tk 3 denotate Call` | remove one annotation per matching task: the one whose text equals the arg (case-insensitive), else the only one containing it, else (no arg) the most recent; several contain it → validation error listing them (exit 1, nothing changed); tasks with no match are skipped; none changed → exit 2; `modified` = now; undoable. Since 0.3.0 |
| info | `tk 7 info` | all fields, local times; one row per annotation; virtual tags (§4) |
| undo | `tk undo` | revert last write cmd (from undo_log) |
| print | `tk +shopping print` | printable HTML page of the matching tasks (A4, black and white): title with the filter, date and time; one section per project (sorted, no project last), tasks by urgency, box to tick (ticked if ended), priority badge `!H`, tags, `due <date>` (+ `today`, or `late` in bold), annotations under the task (small italic, `<date> <text>`, oldest first); 3 empty boxed lines at the end; opened in the browser with the print dialog (print or save as PDF); `--file PATH` saves it without opening; no match → exit 2. Since 0.2.0 |
| export | `tk status:all export > f.json` | TW JSON to stdout, one task per line, incl. `id` (0 if not pending) and `urgency`; waiting tasks always included; no match → `[]`, exit 0 |
| import | `tk import f.json` | TW JSON from FILE, or stdin if none or `-` (UTF-8, or UTF-16 with BOM); merge by uuid; prints added/updated/skipped counts; 1 undo step; any invalid task → nothing imported, error names the task number |
| alias | `tk alias install task` | `install\|remove NAME`: opt-in shim `NAME` (`NAME.cmd` on Windows) running `python -m tame`, in the uv tool bin dir (`UV_TOOL_BIN_DIR`, `XDG_BIN_HOME`, `$XDG_DATA_HOME/../bin`, `~/.local/bin`); marked as tame's: never overwrites/removes other files; warns if the dir is not in PATH or another NAME comes first |
| config | `tk config set undo.retention 1y` | list / `get` / `set` / `unset` (= default) / `path` / `edit` settings (§7) |
| help | `tk help [cmd\|topic]` | no arg: implemented cmds + 1-line summaries; cmd (exact or prefix): usage, text, examples; topics `filters` `dates` `urgency` `settings` (every setting: what it does, values, default; `tk help config KEY` = one setting, plus its current value if config.toml reads; since 0.3.2) `tour` (guided tour; its commands run in order are a test) `license` (TAME's license text + installed libraries with versions and licenses, read from package metadata) `credits` (author Skitourer, thanks, libraries, tools). Topics, not commands: no new command names, so prefixes like `tk l` stay unambiguous. `--help` before `--` = `tk help [<cmd on the line>]`. Works with an invalid config |
| completion | `tk completion powershell` | advanced (not in the `tk help` list; `tk help completion` works): `powershell\|bash` prints the completion script for `tk`, `tame` and the aliases installed by `alias`, for shells or profiles TAME does not manage, dotfiles, or the always-current `tk completion powershell \| Out-String \| Invoke-Expression`. Everyday switch: the `completion` setting (§7). No arg (or extra words) → usage error giving the usage and `tk config set completion true`; unknown shell → usage error listing the shells. Since 0.3.0 |
| version | `tk version` | app + schema version; second line points to `tk help license` / `tk help credits` |

`list` columns: ID Age Project Tags Pri Due Description Urg; hide empty cols; overdue red, due today yellow; `color=false` or non-TTY → plain.

Exit codes: 0 ok, 1 usage error, 2 no match, 3 internal error. Errors → stderr.

**Kind words**: 50 phrases (`kindness.p01`..`p50`, EN + FR) about friends, family, colleagues, free time, nature and not fearing others, each shown as `♥ <phrase>` on its own line after a blank line (italic, dim when colors are on). Shuffled order, all 50 before any repeat; state (`kindness_last`, `kindness_order`) in `meta`, outside undo. They appear: (1) after a successful `list next add done delete modify annotate denotate info undo`, only if stdout is a terminal, at most once every 3 days, then with a 1-in-10 chance per command; (2) when `done` leaves no pending task (terminal only); (3) at the foot of a `print` page opened in the browser (not with `--file`); (4) in an easter egg. Every appearance restarts the 3-day cooldown. Setting `kindness = false` turns off (1)-(3).

**Completion setup** (since 0.3.1): the `completion` setting is the switch. After any successful command run in a terminal (stdout a tty; never in scripts, pipes or tests), TAME aligns the shell profiles with it: `true` → writes or refreshes, `false` → removes, a block between the lines `# >>> tame completion >>>` and `# <<< tame completion <<<` holding the script of `tk completion <shell>`; the rest of the file is never changed (encoding and line endings kept; file and folders created if missing). Profiles: on Windows, `$PROFILE.CurrentUserCurrentHost` of Windows PowerShell and of PowerShell 7 if installed, asked to `powershell`/`pwsh` once and cached in `meta`, and `~/.bashrc` (LF line endings) if Git for Windows' Git Bash is installed (`git-bash.exe` in Git's folder; WSL's `bash.exe` does not count); elsewhere `~/.bashrc` if `$SHELL` is bash. A PowerShell whose execution policy is `Restricted` or `AllSigned` is skipped (profiles would fail at every start) and the user told once. `tk config set|unset completion` and `tk config edit` re-detect the profiles and apply at once, with a message: enabled in `<path>` (open a new terminal), removed from `<path>`, blocked by the execution policy, or no supported shell. While `completion` is false and nothing was ever set up, the first command run in a terminal prints once: `Tip: Tab completion is available: tk config set completion true`.

**Completion protocol** (since 0.3.0): the scripts call the hidden `tk _complete _<current> [words before it...]` (current word prefixed with `_`, so an empty one survives PowerShell 5.1), which prints the candidates, full tokens starting with the current word, one per line, and always exits 0. Never in `tk help`. Fast path: handled in `main()` before parsing; no rich/tomlkit import, database read only, opened read-only and never created. Candidates by context: no command yet → command names, attribute names (`project:` `pri:` `status:` `due.before:` `due.after:`); `+`/`-` → tags of pending tasks and virtual tags (real tags only in `add`/`modify` mods); `project:` → projects of pending tasks; `pri:` → `H M L`; `status:` → statuses and `all`; `due:` `wait:` `due.before:` `due.after:` → date keywords; after `add`/`modify` → mods attributes (`project:` `pri:` `due:` `wait:`); after `help` → commands and topics; `config` → its subcommands, then keys (`get` `set` `unset`), then values for `set` (languages, booleans, `default_command`); `alias` → `install remove`; `completion` → shells; after `--`, `import`, `annotate`, `denotate` → nothing (the shell falls back to file names).

Hidden easter eggs exist: English only, exempt from i18n, kept unreadable in the code (hashed triggers, ROT13/compressed replies); see `tests/cli/test_eggs.py`.

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
kindness = true
default_command = "list"   # list | next: what `tk` alone, or `tk <filter>`, runs
next_limit = 10            # tasks shown by `next`, 1 or more
completion = false         # Tab completion in the shell profile (see below)
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
- Import: JSON array or one object per line. Same uuid → update if incoming `modified` newer, else skip. Missing `uuid` → new one; `entry` → now; `modified` → `entry`; `status` → pending. `id`, `urgency` ignored. New pending tasks get the next ids (by entry); if an update changes which tasks are pending, all are renumbered.
- `annotations`: array of `{entry, description}`, both required, `entry` a TW date → stored natively. Export: array sorted by entry; omitted when empty.
- `depends`: array of uuids, or a comma-separated string (TW < 2.6) → stored natively; duplicates and the task's own uuid dropped. Export: array of uuids, sorted; omitted when empty.
- Invalid `annotations`/`depends` value (wrong type, missing field, bad date or uuid) → whole key kept in `extra` unchanged.
- `wait`, `start`, `until` (TW dates) and `recur` (string) → stored natively; exported when set. Invalid value → kept in `extra` unchanged.
- Other unsupported TW attrs (UDAs…), and a `priority` other than H/M/L → stored in `extra`, re-exported unchanged (TAME fields win).
- TW status `waiting` → `pending` + `wait` (TW 3 style; exported as `pending`); without a valid `wait`, and status `recurring`: `pending`, original in `extra.tw_status`, exported back while the task is still pending.

## 8. Layout, quality, release

Layers: `cli` → `core.service` → `storage`. Only `cli.render` imports rich. `core` returns objects / raises typed errors (`TameError` subclasses), never prints.

```
src/tame/
  __main__.py      # main(): parse → dispatch → exit code
  cli/parser.py    # tokens → (filter, cmd, args)
  cli/commands.py  # 1 func per cmd
  cli/render.py    # rich output
  cli/printout.py  # tk print: HTML page
  core/models.py   # Task dataclass
  core/filters.py  # Filter (syntax-free)
  core/dates.py    # relative date parser
  core/urgency.py
  cli/eggs.py      # hidden extras (§5)
  cli/completion.py # shell completion scripts and candidates (§5)
  core/service.py  # TaskService: add/modify/complete/delete/query/undo/import
  storage/repo.py  # SQLite repo
  storage/migrations.py
  storage/codec.py # datetime <-> DB text
  io/tw_json.py    # Taskwarrior JSON (§7)
  alias.py         # opt-in command aliases
  i18n.py  config.py  errors.py
  locales/en.toml  fr.toml
tests/             # mirrors src; tmp TAME_HOME fixture
scripts/           # tk.ps1/tk.sh sandbox, smoke.py, release_notes.py, spoilers.py
docs/              # SPEC, grammar, commands + site pages (mkdocs.yml); install.ps1/.sh; assets/ (logo: light, dark, site header, favicon SVG; social-preview.png)
.github/workflows/ # ci.yml, docs.yml (Pages), release.yml (PyPI + GitHub release)
```

**Code docs**: Google-style docstrings on public modules/classes/funcs; parser rules commented with rule numbers from §4.

**Tests**: every example in this spec = a test. Focus: parser, dates (frozen clock), urgency, TW round-trip.

**Release rule** (blocking, every release):

- [ ] Documentation matches current behavior **everywhere**: README (incl. badges render), docs site pages (`docs/*.md`, `mkdocs build --strict`), SPEC, `tk help` + tour in every locale (`en.toml`, `fr.toml`), CONTRIBUTING, GitHub About description
- [ ] Docstrings up to date on changed code
- [ ] CHANGELOG updated
- [ ] `en.toml` complete; i18n key test green
- [ ] CI and Docs workflows green (ruff, mypy, pytest, both OS; site built and deployed)
- [ ] Install from GitHub checked (`uv tool install git+…`) on a clean tool dir
- [ ] Version bumped (SemVer) and CHANGELOG `## [X.Y.Z]` section; tag `vX.Y.Z` pushed → `release.yml` publishes to PyPI (approve it) and creates the GitHub release

**Roadmap V1** (1 PR each):

1. Repo skeleton, uv, CI, `tame version`
2. Model + SQLite repo + minimal add/list
3. Hybrid parser + filters
4. done/delete/modify/info
5. Dates + urgency
6. undo
7. Config (7a: `config.toml`, `config` cmd, undo purge; 7b: `help`; 7c: i18n FR)
8. TW import/export + `alias` (8a: `export`/`import`, `status:all`; 8b: `alias`)
9. Extras before release (9a: README; 9b: onboarding; 9c: easter eggs; 9d: badges + coverage gate; 9e: docs site + `docs/commands.md`)
10. Release (10a: install polish, installers, CI install check; 10b: PyPI name + release workflow; 10c: docs pass → v0.1.0)

**Roadmap 0.2.0**: `license`/`credits` help topics; `print`; kind words; GitHub Actions on Node.js 24.

**Roadmap 0.3.0** (1 PR each): schema v2; virtual tags; `next`; `annotate`/`denotate`; `wait:` + schema 3; shell completion. **0.3.1**: `completion` setting. **0.3.2**: `tk help settings`, `tk help config KEY`; logo. **0.3.3**: completion in both PowerShells and Git Bash. Next: `docs/ROADMAP.md`.
