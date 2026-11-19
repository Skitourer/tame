"""SQLite task repository (SPEC §3)."""

import json
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from tame.core.models import Priority, Status, Task
from tame.errors import StorageError
from tame.storage.migrations import migrate

DB_FILENAME = "tasks.db"

_FIELDS = (
    "uuid",
    "id",
    "description",
    "status",
    "project",
    "priority",
    "due",
    "entry",
    "modified",
    "end",
    "extra",
)
_COLUMNS = ", ".join(f'"{name}"' for name in _FIELDS)


@dataclass(frozen=True, slots=True)
class UndoEntry:
    """One ``undo_log`` row: the state to restore to undo a write command.

    Attributes:
        seq: Log sequence number.
        ts: When the command ran.
        cmd: Command name (``add``, ``done``, ``delete``, ``modify``).
        before: ``(uuid, task)`` for each task the command changed; ``task`` is None
            if the command created it.
        ids: Short ids of all pending tasks before the command, if it renumbered them.
    """

    seq: int
    ts: datetime
    cmd: str
    before: tuple[tuple[str, Task | None], ...]
    ids: Mapping[str, int] | None = None


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
            _to_row(task),
        )
        self._insert_tags(task)

    def update(self, task: Task) -> None:
        """Overwrite the stored task having ``task.uuid``, tags included.

        Raises:
            StorageError: If no task has this uuid.
        """
        uuid, *values = _to_row(task)
        assignments = ", ".join(f'"{name}" = ?' for name in _FIELDS[1:])
        cursor = self._conn.execute(
            f"UPDATE tasks SET {assignments} WHERE uuid = ?", (*values, uuid)
        )
        if cursor.rowcount != 1:
            raise StorageError("error.task_not_found", uuid=uuid)
        self._conn.execute("DELETE FROM task_tags WHERE uuid = ?", (uuid,))
        self._insert_tags(task)

    def renumber(self) -> None:
        """Give pending tasks the short ids 1..n by entry time; clear the others' ids."""
        self._conn.execute("UPDATE tasks SET id = NULL WHERE status != 'pending'")
        rows = self._conn.execute(
            "SELECT uuid FROM tasks WHERE status = 'pending' ORDER BY entry, id, uuid"
        ).fetchall()
        self._conn.executemany(
            "UPDATE tasks SET id = ? WHERE uuid = ?",
            [(number, row["uuid"]) for number, row in enumerate(rows, start=1)],
        )

    def restore(self, task: Task) -> None:
        """Store ``task`` as is: update it if its uuid exists, else insert it."""
        if self.get(task.uuid) is None:
            self.insert(task)
        else:
            self.update(task)

    def remove(self, uuid: str) -> None:
        """Delete the task row for good (undo of ``add`` only; ``delete`` is soft)."""
        self._conn.execute("DELETE FROM tasks WHERE uuid = ?", (uuid,))

    def pending_ids(self) -> dict[str, int]:
        """Return ``{uuid: short id}`` for all pending tasks."""
        rows = self._conn.execute("SELECT uuid, id FROM tasks WHERE status = 'pending'")
        return {row["uuid"]: row["id"] for row in rows}

    def set_ids(self, ids: Mapping[str, int]) -> None:
        """Give the tasks in ``ids`` these short ids; clear every other task's id."""
        self._conn.execute("UPDATE tasks SET id = NULL")
        self._conn.executemany(
            "UPDATE tasks SET id = ? WHERE uuid = ?", [(id_, uuid) for uuid, id_ in ids.items()]
        )

    def push_undo(
        self,
        ts: datetime,
        cmd: str,
        before: Sequence[tuple[str, Task | None]],
        ids: Mapping[str, int] | None = None,
    ) -> None:
        """Append an ``undo_log`` row; ``before`` is stored as a JSON snapshot."""
        snapshot: dict[str, Any] = {
            "tasks": [
                {"uuid": uuid, "task": _task_to_json(task) if task else None}
                for uuid, task in before
            ]
        }
        if ids is not None:
            snapshot["ids"] = dict(ids)
        self._conn.execute(
            "INSERT INTO undo_log(ts, cmd, before) VALUES (?, ?, ?)",
            (to_db(ts), cmd, json.dumps(snapshot, sort_keys=True)),
        )

    def last_undo(self) -> UndoEntry | None:
        """Return the most recent ``undo_log`` row, or None if the log is empty."""
        row = self._conn.execute(
            "SELECT seq, ts, cmd, before FROM undo_log ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        snapshot = json.loads(row["before"])
        return UndoEntry(
            seq=row["seq"],
            ts=from_db(row["ts"]),
            cmd=row["cmd"],
            before=tuple(
                (item["uuid"], _task_from_json(item["task"]) if item["task"] else None)
                for item in snapshot["tasks"]
            ),
            ids=snapshot.get("ids"),
        )

    def drop_undo(self, seq: int) -> None:
        """Delete the ``undo_log`` row ``seq``."""
        self._conn.execute("DELETE FROM undo_log WHERE seq = ?", (seq,))

    def prune_undo(self, before: datetime) -> None:
        """Delete the ``undo_log`` rows logged before ``before``."""
        self._conn.execute("DELETE FROM undo_log WHERE ts < ?", (to_db(before),))

    def _insert_tags(self, task: Task) -> None:
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


def _to_row(task: Task) -> tuple[str | int | None, ...]:
    """Return the column values of ``task``, in ``_COLUMNS`` order."""
    return (
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
    )


def _task_to_json(task: Task) -> dict[str, Any]:
    return {**dict(zip(_FIELDS, _to_row(task), strict=True)), "tags": sorted(task.tags)}


def _task_from_json(data: Mapping[str, Any]) -> Task:
    return _to_task(data, frozenset(data["tags"]))


def _to_task(row: Mapping[str, Any] | sqlite3.Row, tags: frozenset[str]) -> Task:
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
