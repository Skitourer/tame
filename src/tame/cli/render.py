"""Terminal output. The only module that imports rich, lazily (SPEC §2 perf)."""

import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from tame.core.models import Task
from tame.i18n import t

if TYPE_CHECKING:
    from rich.console import JustifyMethod

_DATE_FORMAT = "%Y-%m-%d"  # Configurable in roadmap step 7.
_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


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


def print_task_table(tasks: Sequence[Task], now: datetime) -> None:
    """Print ``tasks`` as a table on stdout; columns empty for every task are hidden."""
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
            [task.due.astimezone().strftime(_DATE_FORMAT) if task.due else "" for task in tasks],
        ),
        (t("list.col.description"), "left", [task.description for task in tasks]),
    ]
    shown = [col for col in columns if any(col[2])]

    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, header_style="bold")
    for header, justify, _ in shown:
        table.add_column(header, justify=justify)
    for row in zip(*(cells for _, _, cells in shown), strict=True):
        table.add_row(*row)
    Console(highlight=False).print(table)


def format_local(value: datetime) -> str:
    """Format an aware datetime in local time, to the second."""
    return value.astimezone().strftime(_DATETIME_FORMAT)


def info_rows(task: Task) -> list[tuple[str, str]]:
    """Return the (label, value) rows of ``task`` for ``info``; unset fields are left out.

    Unknown Taskwarrior attributes (``extra``) follow, under their own names.
    """
    rows = [
        (t("info.id"), str(task.id) if task.id is not None else ""),
        (t("info.uuid"), task.uuid),
        (t("info.description"), task.description),
        (t("info.status"), task.status.value),
        (t("info.project"), task.project or ""),
        (t("info.tags"), " ".join(sorted(task.tags))),
        (t("info.priority"), task.priority or ""),
        (t("info.due"), format_local(task.due) if task.due else ""),
        (t("info.entry"), format_local(task.entry)),
        (t("info.modified"), format_local(task.modified)),
        (t("info.end"), format_local(task.end) if task.end else ""),
    ]
    rows += [
        (name, value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
        for name, value in sorted(task.extra.items())
    ]
    return [(label, value) for label, value in rows if value]


def print_task_info(tasks: Sequence[Task]) -> None:
    """Print every field of each task, one two-column table per task."""
    from rich import box
    from rich.console import Console
    from rich.table import Table

    console = Console(highlight=False)
    for index, task in enumerate(tasks):
        if index:
            console.print()
        table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, header_style="bold")
        table.add_column(t("info.col.name"))
        table.add_column(t("info.col.value"))
        for label, value in info_rows(task):
            table.add_row(label, value)
        console.print(table)
