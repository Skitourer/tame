import uuid
from datetime import datetime, timedelta

import pytest

from tame.core.filters import Filter
from tame.core.models import NONE, Changes, Priority, Status
from tame.core.service import TaskService, utc_now
from tame.errors import ValidationError
from tame.storage.repo import TaskRepo


def test_add_sets_fields(service: TaskService, repo: TaskRepo, frozen_now: datetime) -> None:
    task = service.add(" Call bank ", project="home", tags=["phone"], priority="h")

    assert task.id == 1
    assert uuid.UUID(task.uuid).version == 4
    assert task.description == "Call bank"
    assert task.status is Status.PENDING
    assert task.project == "home"
    assert task.tags == frozenset({"phone"})
    assert task.priority is Priority.H
    assert task.entry == task.modified == frozen_now
    assert task.due is None
    assert task.end is None
    assert repo.get(task.uuid) == task


def test_add_assigns_next_id(service: TaskService) -> None:
    ids = [service.add(f"task {n}").id for n in range(3)]
    assert ids == [1, 2, 3]


def test_add_minimal(service: TaskService) -> None:
    task = service.add("Buy milk")
    assert (task.project, task.tags, task.priority) == (None, frozenset(), None)


@pytest.mark.parametrize(
    ("kwargs", "key"),
    [
        ({"description": " "}, "error.empty_description"),
        ({"description": "x", "tags": ["+bad"]}, "error.invalid_tag"),
        ({"description": "x", "project": "a..b"}, "error.invalid_project"),
        ({"description": "x", "priority": "Z"}, "error.invalid_priority"),
    ],
)
def test_add_rejects_invalid(service: TaskService, kwargs: dict[str, object], key: str) -> None:
    with pytest.raises(ValidationError) as exc:
        service.add(**kwargs)  # type: ignore[arg-type]
    assert exc.value.key == key
    assert service.query() == []


def test_query_returns_pending_by_id(service: TaskService) -> None:
    first = service.add("first")
    second = service.add("second")
    assert service.query() == [first, second]


def test_query_with_filter(service: TaskService) -> None:
    service.add("Call bank", tags=["phone"])
    report = service.add("Write report", tags=["phone"], project="work")
    assert service.query(Filter(tags_in=frozenset({"phone"}), project="work")) == [report]
    assert service.query(Filter(status=Status.COMPLETED)) == []


def test_utc_now_is_aware_and_second_precision() -> None:
    now = utc_now()
    assert now.tzinfo is not None
    assert now.microsecond == 0


@pytest.fixture
def later(frozen_now: datetime) -> datetime:
    return frozen_now + timedelta(hours=1)


@pytest.fixture
def later_service(repo: TaskRepo, later: datetime) -> TaskService:
    """A second service on the same repo whose clock is one hour later."""
    return TaskService(repo, clock=lambda: later)


def test_complete_sets_status_end_and_renumbers(
    service: TaskService, later_service: TaskService, repo: TaskRepo, later: datetime
) -> None:
    _, second, _ = (service.add(name) for name in ("one", "two", "three"))
    (done,) = later_service.complete([second])

    assert (done.status, done.id, done.end, done.modified) == (
        Status.COMPLETED,
        None,
        later,
        later,
    )
    assert repo.get(second.uuid) == done
    assert [(t.description, t.id) for t in service.query()] == [("one", 1), ("three", 2)]
    assert service.query(Filter(status=Status.COMPLETED)) == [done]


def test_delete_is_soft(
    service: TaskService, later_service: TaskService, repo: TaskRepo, later: datetime
) -> None:
    task = service.add("one")
    (deleted,) = later_service.delete([task])
    assert (deleted.status, deleted.end) == (Status.DELETED, later)
    assert repo.get(task.uuid) == deleted
    assert service.query() == []


def test_close_skips_tasks_already_in_status(service: TaskService) -> None:
    (done,) = service.complete([service.add("one")])
    assert service.complete([done]) == []
    assert len(service.delete([done])) == 1


def test_add_after_done_uses_next_id(service: TaskService) -> None:
    first, _ = service.add("one"), service.add("two")
    service.complete([first])
    assert service.add("three").id == 2


def test_modify_applies_changes(
    service: TaskService, later_service: TaskService, repo: TaskRepo, later: datetime
) -> None:
    task = service.add("Call bank", project="home", tags=["phone", "x"], priority="H")
    changes = Changes(
        description="Call the bank",
        project="work",
        priority=Priority.L,
        tags_add=frozenset({"urgent"}),
        tags_remove=frozenset({"x", "absent"}),
    )
    (changed,) = later_service.modify([task], changes)

    assert changed.description == "Call the bank"
    assert (changed.project, changed.priority) == ("work", Priority.L)
    assert changed.tags == frozenset({"phone", "urgent"})
    assert (changed.modified, changed.entry, changed.id) == (later, task.entry, 1)
    assert repo.get(task.uuid) == changed


def test_modify_clears_attributes(service: TaskService) -> None:
    task = service.add("x", project="home", priority="H")
    (changed,) = service.modify([task], Changes(project=NONE, priority=NONE))
    assert (changed.project, changed.priority) == (None, None)


def test_modify_skips_unchanged_tasks(service: TaskService) -> None:
    tagged = service.add("a", tags=["phone"])
    plain = service.add("b")
    changed = service.modify([tagged, plain], Changes(tags_add=frozenset({"phone"})))
    assert [task.uuid for task in changed] == [plain.uuid]
    assert service.query()[0] == tagged


def test_changes_truthiness() -> None:
    assert not Changes()
    assert Changes(project=NONE)
    assert Changes(tags_remove=frozenset({"x"}))
