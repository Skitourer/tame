# Roadmap

Planned features, release by release. Guiding rule: **simple by default, powerful on demand**. Every
new feature is invisible until used: plain commands keep working unchanged, power comes from
extra attributes or options, never from mandatory syntax.

Status: proposal. Items move into `SPEC.md` (with tests and docs) in the PR that builds them.
Order within a release = suggested PR order. TW = Taskwarrior.

## 0.3 – everyday comfort, nothing new to learn (released: 0.3.0, completion setting in 0.3.1)

| Feature | Example | Notes |
|---|---|---|
| Schema migration v2 | – | First PR: add `annotations(uuid, entry, description)` and `depends(uuid, depends_on)` tables in one migration, so 0.4 needs no second schema bump. Promote TW `annotations`/`depends` from `extra`. |
| Virtual tags | `tk +OVERDUE list`, `tk +TODAY` | Computed in `core/filters.py`, uppercase, read-only: `OVERDUE TODAY TOMORROW WEEK MONTH DUE BLOCKED UNBLOCKED ANNOTATED PROJECT TAGGED`. Cannot be set with `+X`. No schema change. `WAITING` and `ACTIVE` come later with `wait:` and start/stop. |
| `next` report | `tk next` | Top N pending by urgency (`next_limit`, default 10), compact columns. Candidate default command (`default_command` setting, default stays `list`). |
| Annotations | `tk 3 annotate Call back Monday`, `tk 3 denotate Call` | Timestamped notes; shown in `info`, under the task in `print`, as a count in `list`. `+ANNOTATED`. TW round-trip native. |
| `wait:` | `tk 4 modify wait:mon` | Hidden from `list`/`next` until the date; Adds the `+WAITING` virtual tag (reserved name from then on); `+WAITING` or `status:all` shows them. TW `waiting` status maps to `pending` + `wait`. |
| Shell completion | `tk config set completion true` | Commands, attributes, projects, tags, date keywords. PowerShell and bash. Data from a hidden `tk _complete` command (fast path, no rich import). |

## 0.4 – power on demand

| Feature | Example | Notes |
|---|---|---|
| Dependencies | `tk 5 modify depends:3,4` | `+BLOCKED` while a dependency is pending; blocked tasks lose urgency, blocking tasks gain some (config coeffs). Cycle detection → usage error. |
| Recurrence | `tk add Backup recur:weekly due:fri` | `daily weekly monthly yearly` + `Nd/Nw/Nm`; `until:` optional. Next instance created on `done` (no template task, no background job). TW `recur` imported. |
| start / stop | `tk 3 start`, `tk stop` | `start` timestamp; adds the `+ACTIVE` virtual tag (reserved name from then on); time spent summed in `info`. One active task by default (`multiple_active` setting). Active tasks gain urgency. |
| Advanced filters | `tk '(+phone or +mail) and pri:H'` | `or`, `and`, `not`, parentheses, `/regex/` on description. Only when typed: plain filters parse exactly as today. |

## 0.5 – automate and customize

| Feature | Example | Notes |
|---|---|---|
| Contexts | `tk context lab`, `tk context none` | Named filters in `config.toml` (`[context.lab] filter = "project:lab"`), applied to every read command until changed. Shown in `list` header. |
| Named reports | `tk week` | `[report.week]` in config: filter, columns, sort, limit. Called like a command; `print` accepts them. |
| `--json` output | `tk +phone list --json` | Stable, documented schema for scripts (PowerShell `ConvertFrom-Json`), distinct from TW export. On `list`, `next`, `info`. |
| User attributes (UDA) | `tk add Report effort:2h client:CEA` | Declared in `[uda.<name>]` (type `string/number/date/duration`, optional values list); filterable, sortable, optional urgency coeff. TW UDAs from `extra` become real once declared. |
| Hooks | `on-add`, `on-modify`, `on-done` | Python scripts in `%APPDATA%\tame\hooks\`; receive task JSON on stdin; non-zero exit cancels the change. Off unless the folder has scripts. |
| Statistics | `tk stats` | Created/completed per week, per project, overdue count. Text table; `--json`. |

## Later

- **TUI** (Textual): browse, filter, edit; reuses `TaskService` unchanged (SPEC §1 hard rule).
- Sync between machines (export/merge based; never SQLite on a cloud folder).
- Calendar export (`.ics`) for tasks with a due date.

## Cross-cutting rules

- Every feature: i18n keys (en + fr), `tk help <cmd>`, `docs/commands.md`, tests, CHANGELOG.
- TW compatibility: anything TW knows is imported natively once supported, otherwise kept in
  `extra` (unchanged policy).
- Startup time stays < 250 ms: new features must not import heavy modules on the plain
  `list` path.
- When a release ships, update `SPEC.md` §1 ("In V1" / "Out V1") accordingly.
