import json
import sqlite3
from pathlib import Path

import pytest

from tame.core.models import Annotation
from tame.errors import StorageError
from tame.storage.migrations import SCHEMA_VERSION, migrate, schema_version
from tame.storage.repo import TaskRepo, from_db


def connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path, autocommit=True)


def tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {name for (name,) in rows}


def test_empty_database_is_version_0(tmp_path: Path) -> None:
    assert schema_version(connect(tmp_path / "x.db")) == 0


def test_migrate_creates_schema(tmp_path: Path) -> None:
    conn = connect(tmp_path / "x.db")
    migrate(conn)
    assert schema_version(conn) == SCHEMA_VERSION == 2
    assert {"meta", "tasks", "task_tags", "undo_log", "annotations", "depends"} <= tables(conn)


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "x.db")
    migrate(conn)
    migrate(conn)
    assert schema_version(conn) == SCHEMA_VERSION


def test_newer_database_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    conn = connect(path)
    migrate(conn)
    conn.execute("UPDATE meta SET value = '99' WHERE key = 'schema_version'")
    conn.close()
    with pytest.raises(StorageError) as exc:
        TaskRepo(path)
    assert exc.value.key == "error.db_too_new"
    assert exc.value.params == {"found": 99, "supported": SCHEMA_VERSION}


def test_newer_database_leaves_no_open_transaction(tmp_path: Path) -> None:
    conn = connect(tmp_path / "x.db")
    migrate(conn)
    conn.execute("UPDATE meta SET value = '99' WHERE key = 'schema_version'")
    with pytest.raises(StorageError):
        migrate(conn)
    assert not conn.in_transaction


def test_constraints_enforced(tmp_path: Path) -> None:
    conn = connect(tmp_path / "x.db")
    migrate(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO tasks(uuid, description, status, entry, modified) "
            "VALUES ('u', 'd', 'waiting', 'e', 'm')"
        )


# --- Migration 1 -> 2 ------------------------------------------------------------------

UUID = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
THIRD = "33333333-3333-4333-8333-333333333333"


def v1_database(path: Path, extras: dict[str, dict[str, object] | None]) -> None:
    """Create a schema v1 database holding one pending task per ``extras`` item."""
    conn = connect(path)
    migrate(conn, target_version=1)
    for number, (uuid, extra) in enumerate(extras.items(), start=1):
        conn.execute(
            "INSERT INTO tasks(uuid, id, description, status, entry, modified, extra) "
            "VALUES (?, ?, 'd', 'pending', '2026-11-19T09:30:00Z', '2026-11-19T09:30:00Z', ?)",
            (uuid, number, json.dumps(extra) if extra is not None else None),
        )
    conn.close()


def test_v1_database_is_upgraded(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    notes = [
        {"entry": "20261103T080000Z", "description": "second"},
        {"entry": "20261102T080000Z", "description": "first"},
    ]
    v1_database(
        path,
        {
            UUID: {"annotations": notes, "depends": f"{OTHER},{THIRD}", "wait": "w"},
            OTHER: {"depends": [UUID]},
            THIRD: None,
        },
    )
    with TaskRepo(path) as repo:
        task, other, third = repo.get(UUID), repo.get(OTHER), repo.get(THIRD)
    assert task is not None and other is not None and third is not None
    assert task.annotations == (
        Annotation(from_db("2026-11-02T08:00:00Z"), "first"),
        Annotation(from_db("2026-11-03T08:00:00Z"), "second"),
    )
    assert task.depends == {OTHER, THIRD}
    assert task.extra == {"wait": "w"}
    assert (other.depends, other.extra) == ({UUID}, {})
    assert (third.annotations, third.depends, third.extra) == ((), frozenset(), {})
    conn = connect(path)
    assert schema_version(conn) == 2
    assert conn.execute("SELECT extra FROM tasks WHERE uuid = ?", (OTHER,)).fetchone() == (None,)


def test_upgrade_keeps_invalid_values_in_extra(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    extra: dict[str, object] = {
        "annotations": [{"description": "no entry"}],
        "depends": ["not-a-uuid"],
    }
    v1_database(path, {UUID: extra})
    with TaskRepo(path) as repo:
        task = repo.get(UUID)
    assert task is not None
    assert (task.annotations, task.depends, task.extra) == ((), frozenset(), extra)


def test_upgrade_drops_self_dependency(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    v1_database(path, {UUID: {"depends": [UUID, OTHER]}})
    with TaskRepo(path) as repo:
        task = repo.get(UUID)
    assert task is not None
    assert (task.depends, task.extra) == ({OTHER}, {})


def test_failed_upgrade_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    v1_database(path, {UUID: {"depends": [OTHER]}})
    conn = connect(path)
    conn.execute("CREATE TABLE depends(x)")  # makes migration 2 fail
    conn.close()
    with pytest.raises(StorageError):
        TaskRepo(path)
    conn = connect(path)
    assert schema_version(conn) == 1
    assert "annotations" not in tables(conn)
    assert conn.execute("SELECT extra FROM tasks").fetchone() == (json.dumps({"depends": [OTHER]}),)
