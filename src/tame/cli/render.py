"""Terminal output. The only module that imports rich, lazily (SPEC §2 perf)."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from tame.core.models import Task
from tame.i18n import t

if TYPE_CHECKING:
    from rich.console import JustifyMethod

_DATE_FORMAT = "%Y-%m-%d"  # Configurable in roadmap step 7.


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
        (t("list.col.id"), "right", [str(task.id) for task in tasks]),
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
