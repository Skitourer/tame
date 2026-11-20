"""Terminal output. The only module that imports rich, lazily (SPEC §2 perf)."""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from tame.core.models import Task
from tame.core.urgency import DEFAULT_COEFFICIENTS, Coefficients, urgency
from tame.i18n import t

if TYPE_CHECKING:
    from rich.console import JustifyMethod

DEFAULT_DATE_FORMAT = "%Y-%m-%d"
_TIME_FORMAT = "%H:%M:%S"


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


def row_style(task: Task, now: datetime) -> str | None:
    """Return the row style of ``task``: red if due before today, yellow if due today.

    Days are local calendar days. Rich drops styles when color is off or output is not
    a terminal.
    """
    if task.due is None:
        return None
    due_day, today = task.due.astimezone().date(), now.astimezone().date()
    if due_day < today:
        return "red"
    return "yellow" if due_day == today else None


def print_task_table(
    tasks: Sequence[Task],
    now: datetime,
    *,
    coefficients: Coefficients = DEFAULT_COEFFICIENTS,
    date_format: str = DEFAULT_DATE_FORMAT,
    color: bool = True,
    compact: bool = False,
) -> None:
    """Print ``tasks`` as a table on stdout; columns empty for every task are hidden.

    Args:
        tasks: Tasks, in display order.
        now: Current time, for ages, urgency and due colors.
        coefficients: Urgency weights.
        date_format: strftime format of the Due column.
        color: False to print without colors.
        compact: True to leave out the Age and Tags columns (``next``).
    """
    from rich import box
    from rich.console import Console
    from rich.table import Table

    columns: list[tuple[str, JustifyMethod, list[str]]] = [
        (
            t("list.col.id"),
            "right",
            [str(task.id) if task.id is not None else "" for task in tasks],
        ),
        (t("list.col.age"), "right", [format_age(now - task.entry) for task in tasks]),
        (t("list.col.project"), "left", [task.project or "" for task in tasks]),
        (t("list.col.tags"), "left", [" ".join(sorted(task.tags)) for task in tasks]),
        (t("list.col.priority"), "left", [task.priority or "" for task in tasks]),
        (
            t("list.col.due"),
            "left",
            [task.due.astimezone().strftime(date_format) if task.due else "" for task in tasks],
        ),
        (t("list.col.description"), "left", [_description_cell(task) for task in tasks]),
        (
            t("list.col.urgency"),
            "right",
            [format_urgency(urgency(task, now, coefficients)) for task in tasks],
        ),
    ]
    if compact:
        del columns[3], columns[1]  # Tags, Age.
    shown = [col for col in columns if any(col[2])]

    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, header_style="bold")
    for header, justify, _ in shown:
        table.add_column(header, justify=justify)
    rows = zip(*(cells for _, _, cells in shown), strict=True)
    for task, row in zip(tasks, rows, strict=True):
        table.add_row(*row, style=row_style(task, now))
    Console(highlight=False, no_color=not color).print(table)


def _description_cell(task: Task) -> str:
    """Return the description as rich markup, with the annotation count, dim, if any."""
    from rich.markup import escape

    count = f" [dim]\\[{len(task.annotations)}][/dim]" if task.annotations else ""
    return escape(task.description) + count


def format_local(value: datetime, date_format: str = DEFAULT_DATE_FORMAT) -> str:
    """Format an aware datetime in local time: ``date_format`` then the time, to the second."""
    return value.astimezone().strftime(f"{date_format} {_TIME_FORMAT}")


def info_rows(
    task: Task,
    now: datetime,
    *,
    virtual: frozenset[str] = frozenset(),
    coefficients: Coefficients = DEFAULT_COEFFICIENTS,
    date_format: str = DEFAULT_DATE_FORMAT,
) -> list[tuple[str, str]]:
    """Return the (label, value) rows of ``task`` for ``info``; unset fields are left out.

    ``virtual`` holds the task's virtual tags (SPEC §4), shown after its tags.

    One row per annotation follows, then unknown Taskwarrior attributes (``extra``)
    under their own names.
    """

    def local(value: datetime | None) -> str:
        return format_local(value, date_format) if value else ""

    rows = [
        (t("info.id"), str(task.id) if task.id is not None else ""),
        (t("info.uuid"), task.uuid),
        (t("info.description"), task.description),
        (t("info.status"), task.status.value),
        (t("info.project"), task.project or ""),
        (t("info.tags"), " ".join(sorted(task.tags))),
        (t("info.virtual"), " ".join(sorted(virtual))),
        (t("info.priority"), task.priority or ""),
        (t("info.due"), local(task.due)),
        (t("info.entry"), local(task.entry)),
        (t("info.modified"), local(task.modified)),
        (t("info.end"), local(task.end)),
        (t("info.depends"), " ".join(sorted(task.depends))),
        (t("info.urgency"), format_urgency(urgency(task, now, coefficients))),
    ]
    rows += [
        (t("info.annotation"), f"{local(note.entry)} {note.description}")
        for note in task.annotations
    ]
    rows += [
        (name, value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
        for name, value in sorted(task.extra.items())
    ]
    return [(label, value) for label, value in rows if value]


def print_task_info(
    tasks: Sequence[Task],
    now: datetime,
    *,
    virtual: Mapping[str, frozenset[str]] | None = None,
    coefficients: Coefficients = DEFAULT_COEFFICIENTS,
    date_format: str = DEFAULT_DATE_FORMAT,
    color: bool = True,
) -> None:
    """Print every field of each task, one two-column table per task.

    ``virtual`` maps task uuids to their virtual tags.
    """
    from rich import box
    from rich.console import Console
    from rich.table import Table

    console = Console(highlight=False, no_color=not color)
    for index, task in enumerate(tasks):
        if index:
            console.print()
        table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, header_style="bold")
        table.add_column(t("info.col.name"))
        table.add_column(t("info.col.value"))
        for label, value in info_rows(
            task,
            now,
            virtual=(virtual or {}).get(task.uuid, frozenset()),
            coefficients=coefficients,
            date_format=date_format,
        ):
            table.add_row(label, value)
        console.print(table)
