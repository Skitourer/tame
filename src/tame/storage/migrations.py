"""Schema migrations keyed on ``meta.schema_version`` (SPEC §3)."""

import sqlite3

from tame.errors import StorageError

SCHEMA_VERSION = 1
"""Schema version this code reads and writes."""

_MIGRATIONS: dict[int, tuple[str, ...]] = {
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


def migrate(conn: sqlite3.Connection) -> None:
    """Bring the database to :data:`SCHEMA_VERSION`, one transaction per version.

    ``conn`` must be in autocommit mode. Concurrent callers are serialized by
    ``BEGIN IMMEDIATE``; the version is re-read under the lock.

    Raises:
        StorageError: If the database was created by a newer TAME.
    """
    for target in range(1, SCHEMA_VERSION + 1):
        conn.execute("BEGIN IMMEDIATE")
        try:
            current = schema_version(conn)
            if current > SCHEMA_VERSION:
                raise StorageError("error.db_too_new", found=current, supported=SCHEMA_VERSION)
            if current < target:
                for statement in _MIGRATIONS[target]:
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES ('schema_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(target),),
                )
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
