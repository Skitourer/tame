"""SQLite task repository (SPEC §3)."""

import json
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from tame.core.models import Annotation, Priority, Status, Task
from tame.errors import StorageError
from tame.io.tw_json import PROMOTABLE, split_extra
from tame.storage.codec import from_db, to_db
from tame.storage.migrations import migrate

__all__ = ["DB_FILENAME", "TaskRepo", "UndoEntry", "from_db", "to_db"]

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
    "wait",
    "start",
    "recur",
    "until",
)
_V3_FIELDS = ("wait", "start", "recur", "until")
_BATCH = 500
"""Most uuids bound in one statement (SQLite allows 999 parameters at least)."""
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


class TaskRepo:
    """Task storage in one SQLite file, migrated on open.

    Writes must happen inside :meth:`transaction`.

    Args:
        path: Database file. Parent directories are created if needed.

    Raises:
        StorageError: If the database cannot be opened or migrated.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
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
        """Insert a new task with its tags, annotations and dependencies."""
        self._conn.execute(
            f"INSERT INTO tasks({_COLUMNS}) VALUES ({', '.join('?' * len(_FIELDS))})",
            _to_row(task),
        )
        self._insert_children(task)

    def update(self, task: Task) -> None:
        """Overwrite the stored task having ``task.uuid``, with its side-table rows.

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
        for table in ("task_tags", "annotations", "depends"):
            self._conn.execute(f"DELETE FROM {table} WHERE uuid = ?", (uuid,))
        self._insert_children(task)

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

    def purge(self, uuids: Sequence[str]) -> None:
        """Delete these tasks for good, with their side-table rows and the links to them."""
        for start in range(0, len(uuids), _BATCH):
            chunk = tuple(uuids[start : start + _BATCH])
            marks = ", ".join("?" * len(chunk))
            self._conn.execute(f"DELETE FROM depends WHERE depends_on IN ({marks})", chunk)
            self._conn.execute(f"DELETE FROM tasks WHERE uuid IN ({marks})", chunk)

    def purge_all(self) -> None:
        """Delete every task; ``meta`` (app state, schema version) is kept."""
        for table in ("depends", "annotations", "task_tags", "tasks"):
            self._conn.execute(f"DELETE FROM {table}")

    def clear_undo(self) -> None:
        """Delete the whole ``undo_log``."""
        self._conn.execute("DELETE FROM undo_log")

    def backup(self, target: Path) -> None:
        """Copy the database to ``target`` (SQLite backup API: a consistent snapshot).

        Raises:
            StorageError: If the copy cannot be written.
        """
        try:
            with sqlite3.connect(target) as copy:
                self._conn.backup(copy)
            copy.close()
        except (OSError, sqlite3.Error) as exc:
            raise StorageError("error.backup", path=str(target), detail=str(exc)) from exc

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

    def _insert_children(self, task: Task) -> None:
        self._conn.executemany(
            "INSERT INTO task_tags(uuid, tag) VALUES (?, ?)",
            [(task.uuid, tag) for tag in sorted(task.tags)],
        )
        self._conn.executemany(
            "INSERT INTO annotations(uuid, entry, description) VALUES (?, ?, ?)",
            [
                (task.uuid, to_db(note.entry), note.description)
                for note in sorted(task.annotations, key=lambda note: note.entry)
            ],
        )
        self._conn.executemany(
            "INSERT INTO depends(uuid, depends_on) VALUES (?, ?)",
            [(task.uuid, target) for target in sorted(task.depends)],
        )

    def get(self, uuid: str) -> Task | None:
        """Return the task with this exact uuid, or None."""
        row = self._conn.execute(f"SELECT {_COLUMNS} FROM tasks WHERE uuid = ?", (uuid,)).fetchone()
        if row is None:
            return None
        children = self._children("WHERE uuid = ?", (uuid,))
        return _to_task(row, children.get(uuid, _Children()))

    def by_status(self, status: Status) -> list[Task]:
        """Return all tasks with ``status``, ordered by id then entry."""
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM tasks WHERE status = ? ORDER BY id, entry", (status.value,)
        ).fetchall()
        children = self._children(
            "WHERE uuid IN (SELECT uuid FROM tasks WHERE status = ?)", (status.value,)
        )
        return [_to_task(row, children.get(row["uuid"], _Children())) for row in rows]

    def _children(self, where: str, params: tuple[str, ...]) -> dict[str, "_Children"]:
        """Return the tags, annotations and dependencies of the tasks matching ``where``."""
        result: dict[str, _Children] = {}
        for r in self._conn.execute(f"SELECT uuid, tag FROM task_tags {where}", params):
            result.setdefault(r["uuid"], _Children()).tags.add(r["tag"])
        for r in self._conn.execute(
            f"SELECT uuid, entry, description FROM annotations {where} ORDER BY entry, id", params
        ):
            result.setdefault(r["uuid"], _Children()).annotations.append(
                Annotation(from_db(r["entry"]), r["description"])
            )
        for r in self._conn.execute(f"SELECT uuid, depends_on FROM depends {where}", params):
            result.setdefault(r["uuid"], _Children()).depends.add(r["depends_on"])
        return result

    def get_meta(self, key: str) -> str | None:
        """Return the ``meta`` value stored under ``key``, or None."""
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_meta(self, key: str, value: str) -> None:
        """Store ``value`` under ``key`` in ``meta`` (one statement: atomic on its own)."""
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def max_pending_id(self) -> int:
        """Return the highest short id among pending tasks, 0 if none."""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM tasks WHERE status = 'pending'"
        ).fetchone()
        return int(row[0])


@dataclass(slots=True)
class _Children:
    """Side-table rows of one task."""

    tags: set[str] = field(default_factory=set)
    annotations: list[Annotation] = field(default_factory=list)
    depends: set[str] = field(default_factory=set)


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
        to_db(task.wait) if task.wait else None,
        to_db(task.start) if task.start else None,
        task.recur,
        to_db(task.until) if task.until else None,
    )


def _task_to_json(task: Task) -> dict[str, Any]:
    return {
        **dict(zip(_FIELDS, _to_row(task), strict=True)),
        "tags": sorted(task.tags),
        "annotations": [
            {"entry": to_db(note.entry), "description": note.description}
            for note in task.annotations
        ],
        "depends": sorted(task.depends),
    }


def _task_from_json(data: Mapping[str, Any]) -> Task:
    """Read an undo snapshot.

    One written before schema v3 lacks some fields: they are read from ``extra`` with
    the Taskwarrior import rules.
    """
    missing = [name for name in PROMOTABLE if name not in data]
    children = _Children(
        tags=set(data["tags"]),
        annotations=[
            Annotation(from_db(note["entry"]), note["description"])
            for note in data.get("annotations", ())
        ],
        depends=set(data.get("depends", ())),
    )
    task = _to_task({**dict.fromkeys(_V3_FIELDS), **data}, children)
    if not missing:
        return task
    fields, extra = split_extra(task.extra, task.uuid, missing)
    return replace(task, **fields, extra=extra)


def _to_task(row: Mapping[str, Any] | sqlite3.Row, children: _Children) -> Task:
    return Task(
        uuid=row["uuid"],
        id=row["id"],
        description=row["description"],
        status=Status(row["status"]),
        project=row["project"],
        tags=frozenset(children.tags),
        priority=Priority(row["priority"]) if row["priority"] else None,
        due=from_db(row["due"]) if row["due"] else None,
        entry=from_db(row["entry"]),
        modified=from_db(row["modified"]),
        end=from_db(row["end"]) if row["end"] else None,
        annotations=tuple(children.annotations),
        depends=frozenset(children.depends),
        extra=json.loads(row["extra"]) if row["extra"] else {},
        wait=from_db(row["wait"]) if row["wait"] else None,
        start=from_db(row["start"]) if row["start"] else None,
        recur=row["recur"],
        until=from_db(row["until"]) if row["until"] else None,
    )
