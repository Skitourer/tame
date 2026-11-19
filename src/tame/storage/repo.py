"""SQLite task repository (SPEC §3)."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from tame.core.models import Priority, Status, Task
from tame.errors import StorageError
from tame.storage.migrations import migrate

DB_FILENAME = "tasks.db"

_COLUMNS = 'uuid, id, description, status, project, priority, due, entry, modified, "end", extra'


def to_db(value: datetime) -> str:
    """Format an aware datetime as UTC ISO 8601, e.g. ``2026-11-19T09:30:00Z``."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_db(value: str) -> datetime:
    """Parse a datetime written by :func:`to_db` into an aware UTC datetime."""
    return datetime.fromisoformat(value).astimezone(UTC)


class TaskRepo:
    """Task storage in one SQLite file, migrated on open.

    Writes must happen inside :meth:`transaction`.

    Args:
        path: Database file. Parent directories are created if needed.

    Raises:
        StorageError: If the database cannot be opened or migrated.
    """

    def __init__(self, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(path, autocommit=True)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            migrate(self._conn)
        except (OSError, sqlite3.Error) as exc:
            raise StorageError("error.db_open", path=str(path), detail=str(exc)) from exc

    def close(self) -> None:
        """Close the connection."""
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Run the block in one write transaction; roll back on any exception."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    def insert(self, task: Task) -> None:
        """Insert a new task with its tags."""
        self._conn.execute(
            f"INSERT INTO tasks({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task.uuid,
                task.id,
                task.description,
                task.status.value,
                task.project,
                task.priority.value if task.priority else None,
                to_db(task.due) if task.due else None,
                to_db(task.entry),
                to_db(task.modified),
                to_db(task.end) if task.end else None,
                json.dumps(task.extra, sort_keys=True) if task.extra else None,
            ),
        )
        self._conn.executemany(
            "INSERT INTO task_tags(uuid, tag) VALUES (?, ?)",
            [(task.uuid, tag) for tag in sorted(task.tags)],
        )

    def get(self, uuid: str) -> Task | None:
        """Return the task with this exact uuid, or None."""
        row = self._conn.execute(f"SELECT {_COLUMNS} FROM tasks WHERE uuid = ?", (uuid,)).fetchone()
        if row is None:
            return None
        tags = self._conn.execute("SELECT tag FROM task_tags WHERE uuid = ?", (uuid,)).fetchall()
        return _to_task(row, frozenset(r["tag"] for r in tags))

    def by_status(self, status: Status) -> list[Task]:
        """Return all tasks with ``status``, ordered by id then entry."""
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM tasks WHERE status = ? ORDER BY id, entry", (status.value,)
        ).fetchall()
        tags: dict[str, set[str]] = {}
        for r in self._conn.execute(
            "SELECT tt.uuid, tt.tag FROM task_tags tt JOIN tasks t ON t.uuid = tt.uuid "
            "WHERE t.status = ?",
            (status.value,),
        ):
            tags.setdefault(r["uuid"], set()).add(r["tag"])
        return [_to_task(row, frozenset(tags.get(row["uuid"], ()))) for row in rows]

    def max_pending_id(self) -> int:
        """Return the highest short id among pending tasks, 0 if none."""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM tasks WHERE status = 'pending'"
        ).fetchone()
        return int(row[0])


def _to_task(row: sqlite3.Row, tags: frozenset[str]) -> Task:
    return Task(
        uuid=row["uuid"],
        id=row["id"],
        description=row["description"],
        status=Status(row["status"]),
        project=row["project"],
        tags=tags,
        priority=Priority(row["priority"]) if row["priority"] else None,
        due=from_db(row["due"]) if row["due"] else None,
        entry=from_db(row["entry"]),
        modified=from_db(row["modified"]),
        end=from_db(row["end"]) if row["end"] else None,
        extra=json.loads(row["extra"]) if row["extra"] else {},
    )
