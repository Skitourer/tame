"""Terminal output. The only module that imports rich, lazily (SPEC §2 perf).

Every command writes through this module (SPEC §5 Output style):

- colors come from named roles (``ROLES``), shown only in a terminal, with the
  ``color`` setting on and ``NO_COLOR`` unset;
- in a terminal, a command's output is framed by blank lines (``open_frame`` /
  ``close_frame``) and messages get a symbol: ``✓`` success, ``✗`` error, ``!``
  warning, ``?`` question;
- elsewhere (files, pipes) the text is plain.

Data output (``export``, completion scripts, ``config get``/``path``) does not go
through here: it is printed as is.
"""

import json
import os
import re
import sys
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, TextIO

from tame.core.models import Links, Task
from tame.core.urgency import DEFAULT_COEFFICIENTS, Coefficients, urgency
from tame.i18n import t

if TYPE_CHECKING:
    from rich.console import Console, JustifyMethod
    from rich.text import Text

DEFAULT_DATE_FORMAT = "%Y-%m-%d"
_TIME_FORMAT = "%H:%M:%S"

ROLES: dict[str, str] = {
    "header": "bold",
    "rule": "dim",
    "id": "bold",
    "age": "dim",
    "project": "cyan",
    "tag": "bright_magenta",
    "pri.H": "bold red",
    "pri.M": "yellow",
    "pri.L": "dim",
    "due.overdue": "bold red",
    "due.today": "bold yellow",
    "urgency.high": "bold",
    "urgency.low": "dim",
    "note": "dim",
    "summary": "dim",
    "success": "bold green",
    "error": "bold red",
    "warning": "bold yellow",
    "question": "bold yellow",
    "hint": "dim",
    "heading": "bold underline",
    "command": "cyan",
    "kind": "italic dim",
    # Easter eggs: fixed colors, never themed.
    "egg.heart1": "bold red",
    "egg.heart2": "red",
    "egg.heart3": "magenta",
    "egg.heart4": "bright_magenta",
    "egg.art": "yellow",
    "egg.figure": "cyan",
    "egg.rope": "yellow",
    "egg.caption": "bold green",
    "egg.number": "bold",
    "egg.strong": "bold",
    "egg.soft": "italic",
    "egg.shout": "bold yellow",
    "egg.spark": "bold cyan",
    "egg.yes": "bold green",
    "egg.no": "italic dim",
}
"""Style of each output role, as rich style strings (groundwork for the 0.5 themes).

``egg.*`` roles are the easter eggs' own colors: themes will not change them.
"""

SYMBOLS = {"success": "✓", "error": "✗", "warning": "!", "question": "?"}
"""Prefix of each kind of message, in a terminal only."""

URGENCY_HIGH = 10.0
URGENCY_LOW = 5.0

type Segment = tuple[str, str | None]
"""A piece of a line: its text and its role (None: default style)."""
type Line = Sequence[Segment]


# --- Modes and frame -----------------------------------------------------------------


@dataclass
class _State:
    color: bool = True
    last: TextIO | None = None  # Stream written to last, once the frame is open.


_state = _State()


def is_terminal(stream: TextIO) -> bool:
    """Return True if ``stream`` is a terminal (layout: blank lines and symbols)."""
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def configure(*, color: bool) -> None:
    """Start a command: set the ``color`` setting, forget any open frame."""
    _state.color = color
    _state.last = None


def colors_on(stream: TextIO) -> bool:
    """Return True if colors go to ``stream``: a terminal, ``color`` on, no ``NO_COLOR``."""
    return is_terminal(stream) and _state.color and not os.environ.get("NO_COLOR")


def open_frame(stream: TextIO) -> None:
    """Write the blank line that opens a command's output, once, in a terminal only."""
    if not is_terminal(stream):
        return
    if _state.last is None:
        stream.write("\n")
    _state.last = stream


def close_frame() -> None:
    """Write the blank line that closes a command's output, if it was opened."""
    if _state.last is not None:
        _state.last.write("\n")
        _state.last.flush()
        _state.last = None


def _console(stream: TextIO) -> "Console":
    from rich.console import Console

    return Console(file=stream, highlight=False, no_color=not colors_on(stream))


def _text(line: Line) -> "Text":
    from rich.text import Text

    return Text.assemble(*((text, ROLES[role] if role else "") for text, role in line))


def emit(lines: Sequence[Line], stream: TextIO | None = None) -> None:
    """Print ``lines`` on ``stream`` (stdout by default), styled by role when colors are on."""
    stream = stream or sys.stdout
    open_frame(stream)
    if colors_on(stream):
        console = _console(stream)
        for line in lines:
            console.print(_text(line), soft_wrap=True)
        return
    for line in lines:
        print("".join(text for text, _ in line), file=stream)


def say(text: str, role: str | None = None, *, stream: TextIO | None = None) -> None:
    """Print a plain message (may span lines)."""
    emit([[(line, role)] for line in text.split("\n")], stream)


def _message(kind: str, text: str, role: str | None, stream: TextIO) -> None:
    lines: list[list[Segment]] = [[(line, role)] for line in text.split("\n")]
    if is_terminal(stream):
        lines[0].insert(0, (f"{SYMBOLS[kind]} ", kind))
    emit(lines, stream)


def success(text: str) -> None:
    """Print a success message, ``✓`` first in a terminal."""
    _message("success", text, None, sys.stdout)


def warning(text: str) -> None:
    """Print a warning on stderr, ``!`` first in a terminal."""
    _message("warning", text, None, sys.stderr)


def error(text: str) -> None:
    """Print an error on stderr, ``✗`` first and in red in a terminal."""
    _message("error", text, "error", sys.stderr)


def hint(text: str) -> None:
    """Print a tip or a "nothing changed" message, dim."""
    say(text, "hint")


def ask(question: str, *, yes_no: bool = True) -> str:
    """Ask ``question`` on stdout and return the answer; ``?`` first in a terminal.

    Args:
        question: The question text.
        yes_no: Show the ``(y/N)`` choices after it.

    Raises:
        EOFError: At end of input.
    """
    stream = sys.stdout
    choices = f"{t('confirm.choices')} " if yes_no else ""
    open_frame(stream)
    if colors_on(stream):
        prompt = _text([("? ", "question"), (f"{question} ", None), (choices, "note")])
        return _console(stream).input(prompt)
    prefix = "? " if is_terminal(stream) else ""
    return input(f"{prefix}{question} {choices}")


# --- Formatting ----------------------------------------------------------------------


def format_age(age: timedelta) -> str:
    """Format an age compactly: ``45s``, ``12min``, ``3h``, ``5d``, ``3w``, ``4mo``, ``2y``."""
    seconds = max(int(age.total_seconds()), 0)
    days = seconds // 86_400
    if seconds < 60:
        return t("age.seconds", n=seconds)
    if seconds < 3_600:
        return t("age.minutes", n=seconds // 60)
    if days < 1:
        return t("age.hours", n=seconds // 3_600)
    if days < 14:
        return t("age.days", n=days)
    if days < 90:
        return t("age.weeks", n=days // 7)
    if days < 365:
        return t("age.months", n=days // 30)
    return t("age.years", n=days // 365)


def format_urgency(value: float) -> str:
    """Format an urgency with one decimal."""
    return f"{value:.1f}"


def urgency_role(value: float) -> str | None:
    """Return the role of an urgency: high from 10, low under 5."""
    if value >= URGENCY_HIGH:
        return "urgency.high"
    return "urgency.low" if value < URGENCY_LOW else None


def format_local(value: datetime, date_format: str = DEFAULT_DATE_FORMAT) -> str:
    """Format an aware datetime in local time: ``date_format`` then the time, to the second."""
    return value.astimezone().strftime(f"{date_format} {_TIME_FORMAT}")


def due_state(task: Task, now: datetime) -> str | None:
    """Return ``"overdue"`` if ``task`` is due before today, ``"today"`` if due today.

    Days are local calendar days.
    """
    if task.due is None:
        return None
    due_day, today = task.due.astimezone().date(), now.astimezone().date()
    if due_day < today:
        return "overdue"
    return "today" if due_day == today else None


def relative_day(value: datetime, now: datetime, *, due: bool = False) -> str:
    """Return ``value`` relative to ``now`` in local calendar days: ``3 days ago``, ``today``.

    With ``due``, a past date reads ``overdue by N days``.
    """
    days = (value.astimezone().date() - now.astimezone().date()).days
    if days == 0:
        return t("when.today")
    if days < 0 and due:
        return t("when.overdue_one") if days == -1 else t("when.overdue_many", n=-days)
    if days == -1:
        return t("when.yesterday")
    if days == 1:
        return t("when.tomorrow")
    return t("when.ago", n=-days) if days < 0 else t("when.in", n=days)


def task_ref(task: Task) -> str:
    """Return how a task is named in messages: its short id, else its uuid's first 8 chars."""
    return str(task.id) if task.id is not None else task.uuid[:8]


# --- Task table (list, next) ---------------------------------------------------------


def print_task_table(
    tasks: Sequence[Task],
    now: datetime,
    *,
    coefficients: Coefficients = DEFAULT_COEFFICIENTS,
    date_format: str = DEFAULT_DATE_FORMAT,
    compact: bool = False,
    links: Links | None = None,
) -> None:
    """Print ``tasks`` as a table on stdout; columns empty for every task are hidden.

    Args:
        tasks: Tasks, in display order.
        now: Current time, for ages, urgency and due dates.
        coefficients: Urgency weights.
        date_format: strftime format of the Due column.
        compact: True to leave out the Age, Tags and Dep columns (``next``).
            The Active column (time since ``start``) shows in both.
        links: Dependencies between pending tasks: the Dep column and urgency.
    """
    from rich import box
    from rich.table import Table
    from rich.text import Text

    def cell(text: str, role: str | None = None) -> Text:
        return Text(text, style=ROLES[role] if role else "")

    def alert(task: Task, default: str | None) -> str | None:
        state = due_state(task, now)
        return f"due.{state}" if state else default

    def day(value: datetime | None) -> str:
        return value.astimezone().strftime(date_format) if value else ""

    def scores(task: Task) -> Text:
        value = urgency(task, now, coefficients, links)
        return cell(format_urgency(value), urgency_role(value))

    def running(task: Task) -> str:
        if not task.active or task.start is None:
            return ""
        return format_duration(max(now - task.start, timedelta()))

    def waits_for(task: Task) -> str:
        if links is None:
            return ""
        return ",".join(str(links.ids[uuid]) for uuid in links.pending_depends(task))

    columns: list[tuple[str, JustifyMethod, list[Text]]] = [
        (
            t("list.col.id"),
            "right",
            [
                cell(str(task.id) if task.id is not None else "", alert(task, "id"))
                for task in tasks
            ],
        ),
        (t("list.col.age"), "right", [cell(format_age(now - task.entry), "age") for task in tasks]),
        (t("list.col.project"), "left", [cell(task.project or "", "project") for task in tasks]),
        (t("list.col.tags"), "left", [cell(" ".join(sorted(task.tags)), "tag") for task in tasks]),
        (
            t("list.col.priority"),
            "left",
            [
                cell(task.priority or "", f"pri.{task.priority}" if task.priority else None)
                for task in tasks
            ],
        ),
        (t("list.col.due"), "left", [cell(day(task.due), alert(task, None)) for task in tasks]),
        (t("list.col.wait"), "left", [cell(day(task.wait), "note") for task in tasks]),
        (t("list.col.depends"), "left", [cell(waits_for(task), "id") for task in tasks]),
        (t("list.col.active"), "right", [cell(running(task), "success") for task in tasks]),
        (t("list.col.description"), "left", [description_cell(task) for task in tasks]),
        (t("list.col.urgency"), "right", [scores(task) for task in tasks]),
    ]
    if compact:
        del columns[7], columns[3], columns[1]  # Dep, Tags, Age.
    shown = [col for col in columns if any(text.plain for text in col[2])]

    table = Table(
        box=box.SIMPLE_HEAD,
        show_edge=False,
        pad_edge=False,
        header_style=ROLES["header"],
        border_style=ROLES["rule"],
    )
    for header, justify, _ in shown:
        table.add_column(header, justify=justify)
    for row in zip(*(cells for _, _, cells in shown), strict=True):
        table.add_row(*row)
    open_frame(sys.stdout)
    _console(sys.stdout).print(table)


def format_duration(value: timedelta) -> str:
    """Format a time spent: ``0min``, ``45min``, ``1h20``, ``2d 3h``."""
    minutes = int(value.total_seconds()) // 60
    if minutes < 60:
        return f"{minutes}min"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{minutes:02d}"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


def description_cell(task: Task) -> "Text":
    """Return the description, with the annotation count, dim, if any."""
    from rich.text import Text

    text = Text(task.description)
    if task.annotations:
        text.append(f" [{len(task.annotations)}]", style=ROLES["note"])
    return text


def summary_line(shown: int, tasks: Sequence[Task], now: datetime) -> list[Segment]:
    """Return the line under a task table: ``5 tasks · 1 overdue · 1 due today``.

    ``tasks`` are all the matching tasks, of which the first ``shown`` were printed.
    """
    total = len(tasks)
    if shown < total:
        count = t("list.summary_part", shown=shown, total=total)
    else:
        count = t("list.summary_one") if total == 1 else t("list.summary_many", count=total)
    states = [due_state(task, now) for task in tasks]
    line: list[Segment] = [(count, "summary")]
    for state, key in (("overdue", "list.overdue"), ("today", "list.due_today")):
        if number := states.count(state):
            line += [(" · ", "summary"), (t(key, count=number), f"due.{state}")]
    return line


# --- Task details (info) -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Related:
    """What ``info`` shows about a task's dependencies.

    Attributes:
        depends: The tasks it depends on; a uuid for one that no longer exists.
        blocking: The pending tasks that depend on it.
        links: Dependencies between pending tasks, for urgency.
    """

    depends: Sequence[Task | str] = ()
    blocking: Sequence[Task] = ()
    links: Links | None = None


def _spent(task: Task, now: datetime) -> list[Segment]:
    """``2h15 (3 sessions)``, the current one included; nothing if never started."""
    count = len(task.sessions) + (1 if task.active else 0)
    if not count:
        return []
    key = "info.sessions_one" if count == 1 else "info.sessions_many"
    return [(format_duration(task.time_spent(now)), None), (f"  {t(key, count=count)}", "note")]


def _task_line(task: Task | str) -> list[Segment]:
    """``3 'Buy paint'``, the uuid prefix for a task without id, or a missing uuid."""
    if isinstance(task, str):
        return [(task[:8], "note"), (f"  {t('info.missing')}", "note")]
    return [(task_ref(task), "id"), (f" '{task.description}'", None)]


def info_blocks(
    task: Task,
    now: datetime,
    *,
    virtual: frozenset[str] = frozenset(),
    coefficients: Coefficients = DEFAULT_COEFFICIENTS,
    date_format: str = DEFAULT_DATE_FORMAT,
    related: Related | None = None,
) -> list[list[tuple[str, list[Segment]]]]:
    """Return the blocks of ``info`` lines of ``task``: (label, value) pairs.

    Blocks: the task (status, project, tags then virtual tags, priority, urgency,
    dependencies, the tasks waiting for it, recurrence); its dates, each with a
    relative form; its notes; its uuid and unknown Taskwarrior attributes (``extra``).
    Unset fields and empty blocks are left out.
    """
    related = related or Related()

    def date(value: datetime | None, *, due: bool = False) -> list[Segment]:
        if value is None:
            return []
        state = due_state(task, now) if due and task.end is None else None
        role = f"due.{state}" if state else None
        relative = relative_day(value, now, due=due and task.end is None)
        return [(format_local(value, date_format), role), (f"  {relative}", role or "note")]

    tags: list[Segment] = []
    if task.tags:
        tags.append((" ".join(sorted(task.tags)), "tag"))
    if virtual:
        tags.append((("   " if tags else "") + " ".join(sorted(virtual)), "note"))
    score = urgency(task, now, coefficients, related.links)
    depends: list[tuple[str, list[Segment]]] = [
        (t("info.depends") if index == 0 else "", _task_line(other))
        for index, other in enumerate(related.depends)
    ]
    blocking: list[tuple[str, list[Segment]]] = [
        (t("info.blocking") if index == 0 else "", _task_line(other))
        for index, other in enumerate(related.blocking)
    ]
    main: list[tuple[str, list[Segment]]] = [
        (t("info.status"), [(task.status.value, None)]),
        (t("info.project"), [(task.project, "project")] if task.project else []),
        (t("info.tags"), tags),
        (
            t("info.priority"),
            [(task.priority, f"pri.{task.priority}")] if task.priority else [],
        ),
        (t("info.urgency"), [(format_urgency(score), urgency_role(score))]),
        (t("info.spent"), _spent(task, now)),
        *depends,
        *blocking,
        (t("info.recur"), [(task.recur, None)] if task.recur else []),
    ]
    dates = [
        (t("info.due"), date(task.due, due=True)),
        (t("info.wait"), date(task.wait)),
        (t("info.start"), date(task.start)),
        (t("info.entry"), date(task.entry)),
        (t("info.modified"), date(task.modified)),
        (t("info.end"), date(task.end)),
        (t("info.until"), date(task.until)),
    ]
    notes = [
        (
            t("info.notes") if index == 0 else "",
            [(format_local(note.entry, date_format), "note"), (f"  {note.description}", None)],
        )
        for index, note in enumerate(task.annotations)
    ]
    ids: list[tuple[str, list[Segment]]] = [(t("info.uuid"), [(task.uuid, "note")])]
    ids += [
        (name, [(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), None)])
        for name, value in sorted(task.extra.items())
    ]
    blocks = [
        [(label, value) for label, value in block if value] for block in (main, dates, notes, ids)
    ]
    return [block for block in blocks if block]


def info_lines(
    task: Task,
    now: datetime,
    *,
    virtual: frozenset[str] = frozenset(),
    coefficients: Coefficients = DEFAULT_COEFFICIENTS,
    date_format: str = DEFAULT_DATE_FORMAT,
    related: Related | None = None,
) -> list[list[Segment]]:
    """Return the ``info`` lines of ``task``: title, rule, then blocks of labelled lines."""
    blocks = info_blocks(
        task,
        now,
        virtual=virtual,
        coefficients=coefficients,
        date_format=date_format,
        related=related,
    )
    width = max(len(label) for block in blocks for label, _ in block)
    body: list[list[Segment]] = []
    for block in blocks:
        if body:
            body.append([])
        body += [[(label.rjust(width), "note"), ("  ", None), *value] for label, value in block]
    title: list[Segment] = [
        (t("info.title", task=task_ref(task)), "header"),
        ("  ", None),
        (task.description, "header"),
    ]
    longest = max(sum(len(text) for text, _ in line) for line in [title, *body])
    return [title, [("─" * min(longest, 72), "rule")], *body]


def print_task_info(
    tasks: Sequence[Task],
    now: datetime,
    *,
    virtual: Mapping[str, frozenset[str]] | None = None,
    coefficients: Coefficients = DEFAULT_COEFFICIENTS,
    date_format: str = DEFAULT_DATE_FORMAT,
    related: Mapping[str, Related] | None = None,
) -> None:
    """Print every field of each task, a blank line between tasks.

    ``virtual`` maps task uuids to their virtual tags, ``related`` to their dependencies.
    """
    lines: list[list[Segment]] = []
    for task in tasks:
        if lines:
            lines.append([])
        lines += info_lines(
            task,
            now,
            virtual=(virtual or {}).get(task.uuid, frozenset()),
            coefficients=coefficients,
            date_format=date_format,
            related=(related or {}).get(task.uuid),
        )
    emit(lines)


# --- Help ----------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^([^\W\d_](?:[^\W\d_]|[' -]){0,23}?) ?:(?= |$)")
_EXAMPLE_RE = re.compile(r"^( {2,})(tk\b.*?)(?= {2,}|$)(.*)$")
_COMMAND_RE = re.compile(r"^(  )(\S+)(.*)$")


def _is_label(text: str) -> bool:
    """True if ``text`` reads as a section label: capitalized, three words at most."""
    return text[0].isupper() and len(text.split()) <= 3


def help_line(
    line: str, *, commands: Collection[str] = (), command_labels: Collection[str] = ()
) -> list[Segment]:
    """Return the segments of a help line.

    Section labels (``Examples:``) are headings; the rest of the line is a command after
    a label of ``command_labels`` (``Usage``). Indented ``tk ...`` lines are commands, up
    to two spaces (a comment may follow). ``commands`` names the command list of
    ``tk help``: those names, indented, are commands.
    """
    if (match := _HEADING_RE.match(line)) and _is_label(match.group(1)):
        label = match.group(1)
        rest = line[match.end() :]
        role = "command" if label in command_labels else None
        return [(label, "heading"), (line[len(label) : match.end()], None), (rest, role)]
    if match := _EXAMPLE_RE.match(line):
        return [(match.group(1), None), (match.group(2), "command"), (match.group(3), None)]
    if (match := _COMMAND_RE.match(line)) and match.group(2) in commands:
        return [(match.group(1), None), (match.group(2), "command"), (match.group(3), None)]
    return [(line, None)]


def print_help(text: str, *, commands: Collection[str] = ()) -> None:
    """Print a help text: headings, commands and examples styled when colors are on."""
    labels = {t("help.usage_label", usage="").split(":")[0].strip()}
    emit([help_line(line, commands=commands, command_labels=labels) for line in text.split("\n")])
