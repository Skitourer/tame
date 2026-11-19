import sqlite3
from pathlib import Path

import pytest

from tame.errors import StorageError
from tame.storage.migrations import SCHEMA_VERSION, migrate, schema_version
from tame.storage.repo import TaskRepo


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
    assert schema_version(conn) == SCHEMA_VERSION == 1
    assert {"meta", "tasks", "task_tags", "undo_log"} <= tables(conn)


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
