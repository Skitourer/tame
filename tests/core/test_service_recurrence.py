"""Recurring tasks in the service: add, done, undo, modify, delete (SPEC §4 Recurrence)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from tame.core.filters import ALL, Filter
from tame.core.models import NONE, Changes, Status, TaskRefs
from tame.core.recurrence import ANCHOR
from tame.core.service import TaskService
from tame.errors import ValidationError

FRIDAY = datetime(2026, 11, 20, 12, tzinfo=UTC)  # The day after FROZEN_NOW, at noon.
WEEK = timedelta(days=7)


def test_add_stores_the_period_lowercased(service: TaskService) -> None:
    task = service.add("Backup", due=FRIDAY, recur="Weekly", until=FRIDAY + 4 * WEEK)
    assert (task.recur, task.until, task.extra) == ("weekly", FRIDAY + 4 * WEEK, {})


def test_add_keeps_the_anchor_of_a_monthly_series(service: TaskService) -> None:
    task = service.add("Rent", due=datetime(2027, 1, 31, 12, tzinfo=UTC), recur="monthly")
    assert task.extra == {ANCHOR: 31}


@pytest.mark.parametrize(
    ("kwargs", "key"),
    [
        ({"recur": "weekly"}, "error.recur_needs_due"),
        ({"due": FRIDAY, "until": FRIDAY}, "error.until_needs_recur"),
        ({"due": FRIDAY, "recur": "P1W"}, "error.invalid_recur"),
    ],
)
def test_add_checks_the_rules(service: TaskService, kwargs: dict[str, object], key: str) -> None:
    with pytest.raises(ValidationError) as exc:
        service.add("x", **kwargs)  # type: ignore[arg-type]
    assert exc.value.key == key
    assert service.query() == []


def test_done_creates_the_next_occurrence(service: TaskService) -> None:
    other = service.add("Paint")
    task = service.add(
        "Backup",
        project="home",
        tags=["it"],
        priority="H",
        due=FRIDAY,
        wait=FRIDAY - timedelta(days=1),
        depends=TaskRefs(frozenset({other.id or 0})),
        recur="weekly",
        until=FRIDAY + 4 * WEEK,
    )
    service.annotate([task], "Disk B")
    result = service.done(service.query(Filter(ids=frozenset({2}))))
    assert [done.uuid for done in result.done] == [task.uuid]
    ((old, new),) = result.next
    assert old.uuid == task.uuid
    assert new.uuid != task.uuid
    assert new.status is Status.PENDING
    assert new.id == 2  # Renumbered after Paint (1).
    assert (new.description, new.project, new.tags, new.priority) == (
        "Backup",
        "home",
        frozenset({"it"}),
        task.priority,
    )
    assert (new.due, new.wait) == (FRIDAY + WEEK, FRIDAY + WEEK - timedelta(days=1))
    assert (new.recur, new.until) == ("weekly", FRIDAY + 4 * WEEK)
    assert (new.annotations, new.depends, new.start, new.sessions) == ((), frozenset(), None, ())
    assert service.get(task.uuid).status is Status.COMPLETED  # type: ignore[union-attr]


def test_next_occurrence_skips_missed_dates(service: TaskService) -> None:
    task = service.add("Water plants", due=FRIDAY - 3 * WEEK, recur="weekly")
    ((_, new),) = service.done([task]).next
    assert new.due == FRIDAY


def test_monthly_next_occurrence_keeps_its_anchor(service: TaskService) -> None:
    task = service.add("Rent", due=datetime(2027, 1, 31, 12, tzinfo=UTC), recur="monthly")
    ((_, new),) = service.done([task]).next
    assert new.due is not None
    assert new.due.astimezone().day == 28
    assert new.extra == {ANCHOR: 31}
    ((_, third),) = service.done([new]).next
    assert third.due is not None
    assert third.due.astimezone().day == 31


def test_series_ends_after_until(service: TaskService) -> None:
    task = service.add("Backup", due=FRIDAY, recur="weekly", until=FRIDAY + timedelta(days=3))
    result = service.done([task])
    assert (result.next, [t.uuid for t in result.last]) == ((), [task.uuid])
    assert service.query() == []


def test_unknown_period_gives_no_next_task(service: TaskService, frozen_now: datetime) -> None:
    task = service.add("Imported", due=FRIDAY, recur="weekly")
    imported = service.import_tasks([replace(task, recur="P1W", modified=frozen_now + WEEK)])
    result = service.done(list(imported.updated))
    assert [t.uuid for t in result.unknown] == [task.uuid]
    assert result.next == ()


def test_undo_of_done_removes_the_next_occurrence(service: TaskService) -> None:
    task = service.add("Backup", due=FRIDAY, recur="weekly")
    ((_, new),) = service.done([task]).next
    undone = service.undo()
    assert [t.uuid for t in undone.removed] == [new.uuid]
    assert service.get(new.uuid) is None
    restored = service.get(task.uuid)
    assert restored is not None
    assert (restored.status, restored.id) == (Status.PENDING, 1)


def test_done_of_a_deleted_or_completed_task_creates_nothing(service: TaskService) -> None:
    task = service.add("Backup", due=FRIDAY, recur="weekly")
    (deleted,) = service.delete([task])
    assert service.query() == []
    result = service.done([deleted])
    assert result.next == ()
    assert service.query(Filter(status=ALL)) == [service.get(task.uuid)]


def test_delete_ends_the_series(service: TaskService) -> None:
    task = service.add("Backup", due=FRIDAY, recur="weekly")
    service.delete([task])
    assert service.query() == []


def test_modify_sets_and_ends_a_recurrence(service: TaskService) -> None:
    task = service.add("Rent", due=datetime(2027, 1, 31, 12, tzinfo=UTC))
    (task,) = service.modify([task], Changes(recur="monthly", until=FRIDAY + 52 * WEEK))
    assert (task.recur, task.extra) == ("monthly", {ANCHOR: 31})
    (task,) = service.modify([task], Changes(due=datetime(2027, 2, 15, 12, tzinfo=UTC)))
    assert task.extra == {ANCHOR: 15}
    (task,) = service.modify([task], Changes(recur=NONE))
    assert (task.recur, task.until, task.extra) == (None, None, {})


@pytest.mark.parametrize(
    ("changes", "key"),
    [
        (Changes(due=NONE), "error.recur_needs_due"),
        (Changes(until=NONE, recur="P1W"), "error.invalid_recur"),
    ],
)
def test_modify_checks_the_rules(service: TaskService, changes: Changes, key: str) -> None:
    task = service.add("Backup", due=FRIDAY, recur="weekly")
    with pytest.raises(ValidationError) as exc:
        service.modify([task], changes)
    assert exc.value.key == key


def test_modify_recur_needs_a_due_and_until_a_recur(service: TaskService) -> None:
    task = service.add("Plain")
    for changes, key in [
        (Changes(recur="weekly"), "error.recur_needs_due"),
        (Changes(until=FRIDAY), "error.until_needs_recur"),
    ]:
        with pytest.raises(ValidationError) as exc:
            service.modify([task], changes)
        assert exc.value.key == key


def test_unsetting_due_and_recur_together_is_allowed(service: TaskService) -> None:
    task = service.add("Backup", due=FRIDAY, recur="weekly")
    (task,) = service.modify([task], Changes(due=NONE, recur=NONE))
    assert (task.due, task.recur) == (None, None)


def test_recur_filter_and_virtual_tag(service: TaskService) -> None:
    service.add("Two weeks", due=FRIDAY, recur="biweekly")
    service.add("Weekly", due=FRIDAY, recur="1w")
    service.add("Plain")

    def names(where: Filter) -> list[str]:
        return [task.description for task in service.query(where)]

    assert names(Filter(recur="2w")) == ["Two weeks"]
    assert names(Filter(recur="weekly")) == ["Weekly"]
    assert names(Filter(recur=NONE)) == ["Plain"]
    assert names(Filter(virtual_in=frozenset({"RECURRING"}))) == ["Two weeks", "Weekly"]
    assert names(Filter(virtual_out=frozenset({"RECURRING"}))) == ["Plain"]
