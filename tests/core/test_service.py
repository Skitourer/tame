import uuid
from datetime import datetime

import pytest

from tame.core.filters import Filter
from tame.core.models import Priority, Status
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
