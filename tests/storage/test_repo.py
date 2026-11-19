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


def test_update_overwrites_fields_and_tags(repo: TaskRepo) -> None:
    task = make_task(tags=frozenset({"a", "b"}), project="home")
    with repo.transaction():
        repo.insert(task)
    later = T0 + timedelta(hours=1)
    changed = make_task(
        description="Call bank again",
        status=Status.COMPLETED,
        id=None,
        tags=frozenset({"b", "c"}),
        priority=Priority.L,
        modified=later,
        end=later,
    )
    with repo.transaction():
        repo.update(changed)
    assert repo.get(task.uuid) == changed


def test_update_unknown_uuid_is_storage_error(repo: TaskRepo) -> None:
    with pytest.raises(StorageError) as exc, repo.transaction():
        repo.update(make_task())
    assert exc.value.key == "error.task_not_found"


def test_renumber_by_entry_and_clears_closed_ids(repo: TaskRepo) -> None:
    tasks = [
        make_task(uuid="c", id=1, entry=T0 + timedelta(minutes=2)),
        make_task(uuid="a", id=5, entry=T0),
        make_task(uuid="d", id=2, status=Status.COMPLETED),
        make_task(uuid="b", id=9, entry=T0 + timedelta(minutes=1)),
    ]
    with repo.transaction():
        for task in tasks:
            repo.insert(task)
        repo.renumber()
    assert [(t.uuid, t.id) for t in repo.by_status(Status.PENDING)] == [
        ("a", 1),
        ("b", 2),
        ("c", 3),
    ]
    assert repo.get("d").id is None  # type: ignore[union-attr]


# --- undo support -----------------------------------------------------------------


def test_undo_log_round_trip(repo: TaskRepo) -> None:
    task = make_task(
        tags=frozenset({"a"}), due=T0, priority=Priority.H, extra={"wait": "x"}, project="p"
    )
    with repo.transaction():
        repo.push_undo(T0, "modify", [(task.uuid, task), ("new-uuid", None)], {"u": 1})
    entry = repo.last_undo()
    assert entry is not None
    assert (entry.ts, entry.cmd, entry.ids) == (T0, "modify", {"u": 1})
    assert entry.before == ((task.uuid, task), ("new-uuid", None))


def test_last_undo_is_latest_and_drop_removes_it(repo: TaskRepo) -> None:
    assert repo.last_undo() is None
    with repo.transaction():
        repo.push_undo(T0, "add", [("a", None)])
        repo.push_undo(T0, "done", [("b", None)])
    latest = repo.last_undo()
    assert latest is not None
    assert (latest.cmd, latest.ids) == ("done", None)
    with repo.transaction():
        repo.drop_undo(latest.seq)
    assert repo.last_undo().cmd == "add"  # type: ignore[union-attr]


def test_restore_inserts_or_updates(repo: TaskRepo) -> None:
    task = make_task(tags=frozenset({"a"}))
    with repo.transaction():
        repo.restore(task)
    assert repo.get(task.uuid) == task
    changed = make_task(description="other", tags=frozenset({"b"}))
    with repo.transaction():
        repo.restore(changed)
    assert repo.get(task.uuid) == changed


def test_remove_deletes_task_and_tags(repo: TaskRepo) -> None:
    task = make_task(tags=frozenset({"a"}))
    with repo.transaction():
        repo.insert(task)
        repo.remove(task.uuid)
    assert repo.get(task.uuid) is None
    assert repo.by_status(Status.PENDING) == []


def test_pending_ids_and_set_ids(repo: TaskRepo) -> None:
    with repo.transaction():
        repo.insert(make_task(uuid="a", id=1))
        repo.insert(make_task(uuid="b", id=2))
        repo.insert(make_task(uuid="c", id=None, status=Status.COMPLETED))
    assert repo.pending_ids() == {"a": 1, "b": 2}
    with repo.transaction():
        repo.set_ids({"a": 2, "b": 1})
    assert repo.pending_ids() == {"a": 2, "b": 1}


def test_prune_undo(repo: TaskRepo) -> None:
    with repo.transaction():
        repo.push_undo(T0 - timedelta(days=2), "add", [("old", None)])
        repo.push_undo(T0, "add", [("new", None)])
        repo.prune_undo(T0 - timedelta(days=1))
    entry = repo.last_undo()
    assert entry is not None
    assert entry.before == (("new", None),)
    with repo.transaction():
        repo.drop_undo(entry.seq)
    assert repo.last_undo() is None
