from datetime import UTC, datetime, timedelta

import pytest

from tame.core.models import Priority, Status, Task
from tame.core.urgency import Coefficients, by_urgency, due_factor, urgency

NOW = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)


def make_task(description: str = "x", **fields: object) -> Task:
    values: dict[str, object] = {"entry": NOW, "modified": NOW, **fields}
    return Task(uuid=description, description=description, **values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("days_until_due", "factor"),
    [
        (30, 0.2),
        (14, 0.2),
        (0, 0.2 + 0.8 * 14 / 21),
        (-7, 1.0),
        (-30, 1.0),
        (-3.5, 0.2 + 0.8 * 17.5 / 21),
    ],
)
def test_due_factor(days_until_due: float, factor: float) -> None:
    assert due_factor(NOW + timedelta(days=days_until_due), NOW) == pytest.approx(factor)


def test_new_bare_task_is_zero() -> None:
    assert urgency(make_task(), NOW) == 0.0


@pytest.mark.parametrize(
    ("priority", "score"), [(Priority.H, 6.0), (Priority.M, 3.9), (Priority.L, 1.8)]
)
def test_priority(priority: Priority, score: float) -> None:
    assert urgency(make_task(priority=priority), NOW) == pytest.approx(score)


def test_tags_and_project_count_once() -> None:
    task = make_task(tags=frozenset({"a", "b"}), project="home")
    assert urgency(task, NOW) == pytest.approx(2.0)


def test_age_is_capped_at_one_year() -> None:
    half = make_task(entry=NOW - timedelta(days=365 / 2))
    old = make_task(entry=NOW - timedelta(days=1000))
    assert urgency(half, NOW) == pytest.approx(1.0)
    assert urgency(old, NOW) == pytest.approx(2.0)


def test_due_overdue_week() -> None:
    assert urgency(make_task(due=NOW - timedelta(days=7)), NOW) == pytest.approx(12.0)


def test_sum_with_custom_coefficients() -> None:
    task = make_task(
        priority=Priority.H, due=NOW + timedelta(days=20), tags=frozenset({"a"}), project="p"
    )
    assert urgency(task, NOW) == pytest.approx(6.0 + 12 * 0.2 + 1.0 + 1.0)
    coefficients = Coefficients(pri_H=1.0, due=0.0, tags=0.0, project=0.5)
    assert urgency(task, NOW, coefficients) == pytest.approx(1.5)


def test_by_urgency_highest_first_ties_keep_order() -> None:
    low, high, tie = make_task("low"), make_task("high", priority=Priority.H), make_task("tie")
    assert by_urgency([low, high, tie], NOW) == [high, low, tie]


def test_by_urgency_pending_first() -> None:
    done = make_task("done", priority=Priority.H, status=Status.COMPLETED)
    gone = make_task("gone", priority=Priority.M, status=Status.DELETED)
    low, high = make_task("low"), make_task("high", priority=Priority.L)
    assert by_urgency([done, low, gone, high], NOW) == [high, low, done, gone]
