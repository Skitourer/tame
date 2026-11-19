import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tame.core.models import Priority, Status, Task
from tame.errors import StorageError
from tame.storage.repo import TaskRepo, from_db, to_db

T0 = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)


def make_task(**overrides: object) -> Task:
    fields: dict[str, object] = {
        "uuid": "11111111-1111-4111-8111-111111111111",
        "description": "Call bank",
        "entry": T0,
        "modified": T0,
        "id": 1,
    }
    fields.update(overrides)
    return Task(**fields)  # type: ignore[arg-type]


def test_datetime_round_trip_is_utc() -> None:
    paris = datetime(2026, 11, 19, 10, 30, tzinfo=timezone(timedelta(hours=1)))
    assert to_db(paris) == "2026-11-19T09:30:00Z"
    assert from_db(to_db(paris)) == paris
    assert from_db(to_db(paris)).tzinfo is UTC


def test_insert_get_round_trip_all_fields(repo: TaskRepo) -> None:
    task = make_task(
        project="home.garden",
        tags=frozenset({"phone", "urgent"}),
        priority=Priority.M,
        due=T0 + timedelta(days=2),
        end=T0 + timedelta(hours=1),
        status=Status.COMPLETED,
        id=None,
        extra={"annotations": [{"description": "note"}], "tw_status": "waiting"},
    )
    with repo.transaction():
        repo.insert(task)
    assert repo.get(task.uuid) == task


def test_get_unknown_returns_none(repo: TaskRepo) -> None:
    assert repo.get("nope") is None


def test_by_status_orders_by_id_and_attaches_tags(repo: TaskRepo) -> None:
    a = make_task(uuid="a", id=2, tags=frozenset({"x"}))
    b = make_task(uuid="b", id=1)
    done = make_task(uuid="c", id=None, status=Status.COMPLETED, tags=frozenset({"y"}))
    with repo.transaction():
        for task in (a, b, done):
            repo.insert(task)
    assert repo.by_status(Status.PENDING) == [b, a]
    assert repo.by_status(Status.COMPLETED) == [done]
    assert repo.by_status(Status.DELETED) == []


def test_max_pending_id(repo: TaskRepo) -> None:
    assert repo.max_pending_id() == 0
    with repo.transaction():
        repo.insert(make_task(uuid="a", id=4))
        repo.insert(make_task(uuid="b", id=None, status=Status.DELETED))
    assert repo.max_pending_id() == 4


def test_transaction_rolls_back_on_error(repo: TaskRepo) -> None:
    with pytest.raises(RuntimeError), repo.transaction():
        repo.insert(make_task())
        raise RuntimeError
    assert repo.get(make_task().uuid) is None


def test_duplicate_uuid_is_rejected(repo: TaskRepo) -> None:
    with repo.transaction():
        repo.insert(make_task())
    with pytest.raises(sqlite3.IntegrityError), repo.transaction():
        repo.insert(make_task())


def test_data_persists_across_connections(tmp_path: Path) -> None:
    path = tmp_path / "db" / "tasks.db"
    with TaskRepo(path) as repo, repo.transaction():
        repo.insert(make_task())
    with TaskRepo(path) as repo:
        assert repo.get(make_task().uuid) == make_task()


def test_open_failure_is_storage_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a dir")
    with pytest.raises(StorageError) as exc:
        TaskRepo(blocker / "tasks.db")
    assert exc.value.key == "error.db_open"
