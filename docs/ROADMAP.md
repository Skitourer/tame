# Roadmap

Planned features, release by release. Guiding rule: **simple by default, powerful on demand**. Every
new feature is invisible until used: plain commands keep working unchanged, power comes from
extra attributes or options, never from mandatory syntax.

Status: proposal. Items move into `SPEC.md` (with tests and docs) in the PR that builds them.
Order within a release = suggested PR order. TW = Taskwarrior.

## 0.3 – everyday comfort, nothing new to learn (released: 0.3.0; completion setting in 0.3.1; help on settings and logo in 0.3.2; completion in both PowerShells and Git Bash in 0.3.3)

| Feature | Example | Notes |
|---|---|---|
| Schema migration v2 | – | First PR: add `annotations(uuid, entry, description)` and `depends(uuid, depends_on)` tables in one migration, so 0.4 needs no second schema bump. Promote TW `annotations`/`depends` from `extra`. |
| Virtual tags | `tk +OVERDUE list`, `tk +TODAY` | Computed in `core/filters.py`, uppercase, read-only: `OVERDUE TODAY TOMORROW WEEK MONTH DUE BLOCKED UNBLOCKED ANNOTATED PROJECT TAGGED`. Cannot be set with `+X`. No schema change. `WAITING` and `ACTIVE` come later with `wait:` and start/stop. |
| `next` report | `tk next` | Top N pending by urgency (`next_limit`, default 10), compact columns. Candidate default command (`default_command` setting, default stays `list`). |
| Annotations | `tk 3 annotate Call back Monday`, `tk 3 denotate Call` | Timestamped notes; shown in `info`, under the task in `print`, as a count in `list`. `+ANNOTATED`. TW round-trip native. |
| `wait:` | `tk 4 modify wait:mon` | Hidden from `list`/`next` until the date; Adds the `+WAITING` virtual tag (reserved name from then on); `+WAITING` or `status:all` shows them. TW `waiting` status maps to `pending` + `wait`. |
| Shell completion | `tk config set completion true` | Commands, attributes, projects, tags, date keywords. PowerShell and bash. Data from a hidden `tk _complete` command (fast path, no rich import). |

## 0.3.4 – readable output (released: 0.3.4)

| Feature | Example | Notes |
|---|---|---|
| Output styling | `tk list`, `tk info`, `tk help` | One shared, sober style for every table and long text (`list`, `next`, `info`, `help`, `config`, messages), style "A" of the mockups: a blank line before and after each output (clear break from the shell prompt); bold header over a dim rule; one fixed color per column (project cyan, tags magenta, priority H red / M yellow / L dim, high urgency bold, low dim; no ANSI blue, unreadable on black); overdue/today colors only on the due date and id, not the whole row; dim summary line (`5 tasks · 1 overdue · 1 due today`); `info` grouped (task, dates, notes) with dim right-aligned labels; messages prefixed `✓` success, `✗` error, `?` question. Built on named style roles (see `theme` in 0.5), none exposed yet. `color = false`, non-TTY or `NO_COLOR` → plain, unchanged. No new command. |
| Data security doc | `tk help security` | Explains that the database is not encrypted by TAME and how to protect it with Windows tools: BitLocker (whole disk) or EFS (`cipher /e` on `%APPDATA%\tame`). Also in `docs/` and README. Encryption inside TAME is deliberately out of scope (stdlib `sqlite3` has no encryption; decrypting to a temp file would leave plaintext on disk and add a password prompt and a slow key derivation to every command). |

## 0.4 – power on demand

| Feature | Example | Notes |
|---|---|---|
| purge (released: 0.3.6) | `tk purge`, `tk purge --all` | `purge` permanently removes `deleted` tasks (TW semantics), one y/N prompt (`--yes` skips). `purge --all` empties the whole database: y/N prompt, then the user must type the word `purge`; `--yes` never skips this second step; non-TTY stdin → usage error. Before any purge, a timestamped copy `tame-YYYYMMDD-HHMMSS.db.bak` is written next to the database and its path printed. Not undoable: clears `undo_log`. |
| Dependencies (done) | `tk 5 modify depends:3,4` | `+BLOCKED` while a dependency is pending; blocked tasks lose urgency, blocking tasks gain some (config coeffs). Cycle detection → usage error. |
| Recurrence (done) | `tk add Backup recur:weekly due:fri` | `daily weekly biweekly monthly quarterly yearly annual weekdays` + `Nd/Nw/Nm/Ny`; `until:` optional. Next instance created on `done` from the planned due (no template task, no background job); monthly day kept. TW recurring series converted on import. |
| start / stop (done) | `tk 3 start`, `tk stop` | `start` timestamp; adds the `+ACTIVE` virtual tag (reserved name from then on); time spent summed in `info`. One active task by default (`multiple_active` setting). Active tasks gain urgency. |
| Advanced filters | `tk '(+phone or +mail) and pri:H'` | `or`, `and`, `not`, parentheses, `/regex/` on description. Only when typed: plain filters parse exactly as today. |

## 0.5 – automate and customize

| Feature | Example | Notes |
|---|---|---|
| Contexts | `tk context lab`, `tk context none` | Named filters in `config.toml` (`[context.lab] filter = "project:lab"`), applied to every read command until changed. Shown in `list` header. |
| Named reports | `tk week` | `[report.week]` in config: filter, columns, sort, limit. Called like a command; `print` accepts them. |
| `--json` output | `tk +phone list --json` | Stable, documented schema for scripts (PowerShell `ConvertFrom-Json`), distinct from TW export. On `list`, `next`, `info`. |
| User attributes (UDA) | `tk add Report effort:2h client:CEA` | Declared in `[uda.<name>]` (type `string/number/date/duration`, optional values list); filterable, sortable, optional urgency coeff. TW UDAs from `extra` become real once declared. |
| Hooks | `on-add`, `on-modify`, `on-done` | Python scripts in `%APPDATA%\tame\hooks\`; receive task JSON on stdin; non-zero exit cancels the change. Off unless the folder has scripts. |
| Themes | `tk config set theme mono` | `theme` setting: a built-in name (`default` = 0.3.4 style, `mono` bold/dim + red for overdue only, `boxed` rounded frames, `stripes` header band + striped rows) or a path to a TOML theme file (`base = "default"` then overrides). A `[theme]` table in `config.toml` overrides single roles on top. Roles map to rich style strings (`project = "bold green"`): `header rule id age project tag pri.H pri.M pri.L due.overdue due.today urgency.high urgency.low note summary success error warning question hint heading command kind`. Layout switches, closed list: `spacing`, `stripes`, `box = none\|rounded`, `symbols = true\|false` (words instead). Unknown role, bad style or missing file → usage error naming key and file. Loaded in the render layer only. `tk help theme` lists roles and built-ins. Easter eggs keep their own `egg.*` colors. |
| Statistics | `tk stats` | Created/completed per week, per project, overdue count. Text table; `--json`. |

## Later

- **TUI** (Textual): browse, filter, edit; reuses `TaskService` unchanged (SPEC §1 hard rule).
- Sync between machines (export/merge based; never SQLite on a cloud folder).
- Encrypted export (`tk export --encrypt`, passphrase) for backups and transfer between machines, together with sync.
- Calendar export (`.ics`) for tasks with a due date.

## Cross-cutting rules

- Every feature: i18n keys (en + fr), `tk help <cmd>`, `docs/commands.md`, tests, CHANGELOG.
- TW compatibility: anything TW knows is imported natively once supported, otherwise kept in
  `extra` (unchanged policy).
- Startup time stays < 250 ms: new features must not import heavy modules on the plain
  `list` path.
- When a release ships, update `SPEC.md` §1 ("In V1" / "Out V1") accordingly.
