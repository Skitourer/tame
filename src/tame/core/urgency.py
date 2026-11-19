"""Task urgency (SPEC §6): a weighted sum, higher = more urgent."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from tame.core.models import Priority, Task

_DAY = timedelta(days=1)
_YEAR = timedelta(days=365)


@dataclass(frozen=True, slots=True)
class Coefficients:
    """Urgency weights (``[urgency]`` in the config, roadmap step 7)."""

    pri_H: float = 6.0  # noqa: N815 - config key name
    pri_M: float = 3.9  # noqa: N815
    pri_L: float = 1.8  # noqa: N815
    due: float = 12.0
    age: float = 2.0
    tags: float = 1.0
    project: float = 1.0


DEFAULT_COEFFICIENTS = Coefficients()


def due_factor(due: datetime, now: datetime) -> float:
    """Return 0.2 for a due date 14+ days ahead, rising linearly to 1.0 at 7+ days overdue."""
    overdue_days = (now - due) / _DAY
    if overdue_days >= 7:
        return 1.0
    if overdue_days <= -14:
        return 0.2
    return 0.2 + 0.8 * (overdue_days + 14) / 21


def urgency(task: Task, now: datetime, coefficients: Coefficients = DEFAULT_COEFFICIENTS) -> float:
    """Return the urgency of ``task`` at ``now``.

    Sum of: priority weight; ``due`` * :func:`due_factor`; ``age`` * age in years
    (capped at 1); ``tags`` if any tag; ``project`` if a project is set.
    """
    c = coefficients
    score = {Priority.H: c.pri_H, Priority.M: c.pri_M, Priority.L: c.pri_L, None: 0.0}[
        task.priority
    ]
    if task.due is not None:
        score += c.due * due_factor(task.due, now)
    score += c.age * min(max((now - task.entry) / _YEAR, 0.0), 1.0)
    if task.tags:
        score += c.tags
    if task.project:
        score += c.project
    return score


def by_urgency(tasks: list[Task], now: datetime) -> list[Task]:
    """Return ``tasks`` sorted by urgency, highest first; ties keep their order."""
    return sorted(tasks, key=lambda task: -urgency(task, now))
