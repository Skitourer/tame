"""Recurrence periods and next due dates (SPEC §4 Recurrence).

A recurring task is its own series: completing it creates the next one. Dates move on
the local calendar, keeping the due's local time; monthly and yearly series keep their
day of month (the *anchor*) in ``extra``, so Jan 31 → Feb 28 → Mar 31.
"""

import calendar
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Literal

from tame.core.dates import add_months, localize
from tame.core.models import NONE, Task
from tame.errors import ValidationError

ANCHOR = "recur_anchor"
"""``extra`` key holding the day of month (1-31) of a monthly or yearly series."""


@dataclass(frozen=True, slots=True)
class Period:
    """A recurrence period: ``count`` days, calendar months, or weekdays (Mon-Fri)."""

    unit: Literal["days", "months", "weekdays"]
    count: int


NAMED_PERIODS = {
    "daily": Period("days", 1),
    "weekly": Period("days", 7),
    "biweekly": Period("days", 14),
    "monthly": Period("months", 1),
    "quarterly": Period("months", 3),
    "yearly": Period("months", 12),
    "annual": Period("months", 12),
    "weekdays": Period("weekdays", 1),
}
"""Period names, in the order completion offers them."""

_COUNT_RE = re.compile(r"([1-9]\d{0,3})([dwmy])")
_UNITS: dict[str, tuple[Literal["days", "months"], int]] = {
    "d": ("days", 1),
    "w": ("days", 7),
    "m": ("months", 1),
    "y": ("months", 12),
}


def parse_period(text: str) -> Period | None:
    """Return the period ``text`` names (case-insensitive), or None if TAME does not know it."""
    word = text.strip().lower()
    if word in NAMED_PERIODS:
        return NAMED_PERIODS[word]
    if match := _COUNT_RE.fullmatch(word):
        unit, size = _UNITS[match[2]]
        return Period(unit, int(match[1]) * size)
    return None


def check_recur(text: str) -> str:
    """Return ``text`` lowercased if it is a period TAME knows.

    Raises:
        ValidationError: If it is not.
    """
    if parse_period(text) is None:
        raise ValidationError("error.invalid_recur", value=text)
    return text.strip().lower()


def same_period(stored: str | None, wanted: str) -> bool:
    """True if the task's ``recur`` matches the filter value ``recur:wanted``.

    Known periods compare by meaning (``2w`` = ``biweekly``); others as text,
    case-insensitive. ``wanted`` empty (``NONE``) matches tasks without recurrence.
    """
    if wanted == NONE:
        return stored is None
    if stored is None:
        return False
    mine, theirs = parse_period(stored), parse_period(wanted)
    if mine is not None and theirs is not None:
        return mine == theirs
    return stored.strip().casefold() == wanted.strip().casefold()


def anchored(task: Task, tz: tzinfo | None = None) -> Task:
    """Return ``task`` with its anchor set from ``due`` (monthly/yearly) or removed."""
    extra = {key: value for key, value in task.extra.items() if key != ANCHOR}
    period = parse_period(task.recur) if task.recur else None
    if period is not None and period.unit == "months" and task.due is not None:
        extra[ANCHOR] = task.due.astimezone(tz).day
    return task if extra == task.extra else replace(task, extra=extra)


def next_due(task: Task, now: datetime, tz: tzinfo | None = None) -> datetime | None:
    """Return the first due date of ``task``'s series after ``now``.

    Starts from ``task.due`` and adds the period until the date is after ``now``
    (missed occurrences are skipped).

    Returns:
        An aware UTC datetime, or None if the task has no due or a period TAME does not know.
    """
    period = parse_period(task.recur) if task.recur else None
    if period is None or task.due is None:
        return None
    start = task.due.astimezone(tz).replace(tzinfo=None)
    anchor = task.extra.get(ANCHOR)
    day = anchor if isinstance(anchor, int) and 1 <= anchor <= 31 else start.day
    step = 0
    candidate = start
    while True:
        step += 1
        if period.unit == "days":
            candidate = start + timedelta(days=period.count * step)
        elif period.unit == "months":
            candidate = add_months(start, period.count * step, day)
        else:
            candidate += timedelta(days=1)
            while calendar.weekday(candidate.year, candidate.month, candidate.day) >= 5:
                candidate += timedelta(days=1)
        result = localize(candidate, tz).astimezone(UTC)
        if result > now:
            return result
