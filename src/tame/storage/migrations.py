"""Schema migrations keyed on ``meta.schema_version`` (SPEC §3)."""

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime

from tame.errors import StorageError
from tame.io.tw_json import ANNOTATIONS, DEPENDS, split_extra
from tame.storage.codec import to_db

SCHEMA_VERSION = 3
"""Schema version this code reads and writes."""

type Step = str | Callable[[sqlite3.Connection], None]
"""A migration step: an SQL statement, or a function run on the connection."""


def _promote_annotations_and_depends(conn: sqlite3.Connection) -> None:
    """Move Taskwarrior ``annotations``/``depends`` from ``extra`` to their tables."""
    rows = conn.execute("SELECT uuid, extra FROM tasks WHERE extra IS NOT NULL").fetchall()
    for uuid, extra_json in rows:
        extra = json.loads(extra_json)
        fields, rest = split_extra(extra, uuid, (ANNOTATIONS, DEPENDS))
        if rest == extra:
            continue
        conn.executemany(
            "INSERT INTO annotations(uuid, entry, description) VALUES (?, ?, ?)",
            [(uuid, to_db(note.entry), note.description) for note in fields.get(ANNOTATIONS, ())],
        )
        conn.executemany(
            "INSERT INTO depends(uuid, depends_on) VALUES (?, ?)",
            [(uuid, target) for target in sorted(fields.get(DEPENDS, ()))],
        )
        conn.execute(
            "UPDATE tasks SET extra = ? WHERE uuid = ?",
            (json.dumps(rest, sort_keys=True) if rest else None, uuid),
        )


_V3_FIELDS = ("wait", "start", "recur", "until")


def _promote_wait_start_recur_until(conn: sqlite3.Connection) -> None:
    """Move Taskwarrior ``wait``/``start``/``recur``/``until`` from ``extra`` to columns."""
    rows = conn.execute("SELECT uuid, extra FROM tasks WHERE extra IS NOT NULL").fetchall()
    for uuid, extra_json in rows:
        extra = json.loads(extra_json)
        fields, rest = split_extra(extra, uuid, _V3_FIELDS)
        if rest == extra:
            continue
        values = [fields.get(name) for name in _V3_FIELDS]
        conn.execute(
            'UPDATE tasks SET wait = ?, start = ?, recur = ?, "until" = ?, extra = ? '
            "WHERE uuid = ?",
            (
                *(to_db(v) if isinstance(v, datetime) else v for v in values),
                json.dumps(rest, sort_keys=True) if rest else None,
                uuid,
            ),
        )


_MIGRATIONS: dict[int, tuple[Step, ...]] = {
    1: (
        "CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)",
        """CREATE TABLE tasks(
            uuid TEXT PRIMARY KEY,
            id INTEGER,
            description TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending', 'completed', 'deleted')),
            project TEXT,
            priority TEXT CHECK(priority IN ('H', 'M', 'L')),
            due TEXT,
            entry TEXT NOT NULL,
            modified TEXT NOT NULL,
            "end" TEXT,
            extra TEXT
        )""",
        "CREATE INDEX idx_tasks_status ON tasks(status)",
        """CREATE TABLE task_tags(
            uuid TEXT REFERENCES tasks(uuid) ON DELETE CASCADE,
            tag TEXT,
            PRIMARY KEY(uuid, tag)
        )""",
        """CREATE TABLE undo_log(
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            cmd TEXT NOT NULL,
            before TEXT NOT NULL
        )""",
    ),
    2: (
        """CREATE TABLE annotations(
            id INTEGER PRIMARY KEY,
            uuid TEXT NOT NULL REFERENCES tasks(uuid) ON DELETE CASCADE,
            entry TEXT NOT NULL,
            description TEXT NOT NULL
        )""",
        "CREATE INDEX idx_annotations_uuid ON annotations(uuid)",
        """CREATE TABLE depends(
            uuid TEXT NOT NULL REFERENCES tasks(uuid) ON DELETE CASCADE,
            depends_on TEXT NOT NULL,
            PRIMARY KEY(uuid, depends_on),
            CHECK(uuid <> depends_on)
        )""",
        _promote_annotations_and_depends,
    ),
    3: (
        "ALTER TABLE tasks ADD COLUMN wait TEXT",
        "ALTER TABLE tasks ADD COLUMN start TEXT",
        "ALTER TABLE tasks ADD COLUMN recur TEXT",
        'ALTER TABLE tasks ADD COLUMN "until" TEXT',
        _promote_wait_start_recur_until,
    ),
}


def schema_version(conn: sqlite3.Connection) -> int:
    """Return the schema version of the database, 0 for an empty database."""
    has_meta = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
    ).fetchone()
    if has_meta is None:
        return 0
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    return int(row[0]) if row else 0


def migrate(conn: sqlite3.Connection, target_version: int = SCHEMA_VERSION) -> None:
    """Bring the database to ``target_version``, one transaction per version.

    ``conn`` must be in autocommit mode. Concurrent callers are serialized by
    ``BEGIN IMMEDIATE``; the version is re-read under the lock.

    Args:
        conn: The connection.
        target_version: Version to reach; tests use a lower one to build old databases.

    Raises:
        StorageError: If the database was created by a newer TAME.
    """
    for target in range(1, target_version + 1):
        conn.execute("BEGIN IMMEDIATE")
        try:
            current = schema_version(conn)
            if current > SCHEMA_VERSION:
                raise StorageError("error.db_too_new", found=current, supported=SCHEMA_VERSION)
            if current < target:
                for step in _MIGRATIONS[target]:
                    if isinstance(step, str):
                        conn.execute(step)
                    else:
                        step(conn)
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES ('schema_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(target),),
                )
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
