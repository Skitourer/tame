"""Task use cases. Returns objects and raises ``TameError``; never prints."""

import uuid as uuid_lib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from tame.core.dates import utc_now
from tame.core.filters import Filter
from tame.core.models import (
    Changes,
    Status,
    Task,
    check_description,
    check_project,
    check_tag,
    parse_priority,
)
from tame.errors import NoMatchError
from tame.storage.repo import TaskRepo

Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class UndoResult:
    """What :meth:`TaskService.undo` reverted.

    Attributes:
        cmd: Name of the undone command.
        restored: Tasks put back in their previous state, as now stored.
        removed: Tasks the undone command had created, as they were before removal.
    """

    cmd: str
    restored: tuple[Task, ...]
    removed: tuple[Task, ...]


@dataclass(frozen=True, slots=True)
class ImportResult:
    """What :meth:`TaskService.import_tasks` did.

    Attributes:
        added: Tasks with a new uuid, as stored.
        updated: Existing tasks replaced by a more recently modified version, as stored.
        skipped: Incoming tasks not newer than the stored version.
    """

    added: tuple[Task, ...]
    updated: tuple[Task, ...]
    skipped: tuple[Task, ...]


class TaskService:
    """Entry point for task operations, shared by the CLI and a future TUI.

    Args:
        repo: Open task repository.
        clock: Returns the current aware datetime; injected for tests.
        undo_retention: Undo history older than this is purged on each write; None keeps all.
    """

    def __init__(
        self, repo: TaskRepo, clock: Clock = utc_now, undo_retention: timedelta | None = None
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._undo_retention = undo_retention

    def add(
        self,
        description: str,
        *,
        project: str | None = None,
        tags: Iterable[str] = (),
        priority: str | None = None,
        due: datetime | None = None,
    ) -> Task:
        """Create a pending task with the next free short id.

        Args:
            description: Task text; surrounding whitespace is stripped.
            project: Dotted project name.
            tags: Tag names, without leading ``+``.
            priority: H, M or L (any case).
            due: Due date (aware).

        Returns:
            The stored task.

        Raises:
            ValidationError: If a value is invalid.
        """
        now = self._clock()
        task = Task(
            uuid=str(uuid_lib.uuid4()),
            description=check_description(description),
            entry=now,
            modified=now,
            project=check_project(project) if project is not None else None,
            tags=frozenset(check_tag(tag) for tag in tags),
            priority=parse_priority(priority) if priority is not None else None,
            due=due,
        )
        with self._repo.transaction():
            task = replace(task, id=self._repo.max_pending_id() + 1)
            self._repo.insert(task)
            self._log(now, "add", [(task.uuid, None)])
        return task

    def complete(self, tasks: Iterable[Task]) -> list[Task]:
        """Mark ``tasks`` completed (``end`` = now), then renumber pending tasks.

        Tasks already completed are skipped.

        Returns:
            The changed tasks, as stored.
        """
        return self._close(tasks, Status.COMPLETED, "done")

    def delete(self, tasks: Iterable[Task]) -> list[Task]:
        """Soft-delete ``tasks`` (``end`` = now), then renumber pending tasks.

        Tasks already deleted are skipped.

        Returns:
            The changed tasks, as stored.
        """
        return self._close(tasks, Status.DELETED, "delete")

    def _close(self, tasks: Iterable[Task], status: Status, cmd: str) -> list[Task]:
        now = self._clock()
        changed = [
            replace(task, status=status, id=None, end=now, modified=now)
            for task in tasks
            if task.status is not status
        ]
        if not changed:
            return []
        with self._repo.transaction():
            ids = self._repo.pending_ids()
            self._log(now, cmd, self._snapshot(changed), ids)
            for task in changed:
                self._repo.update(task)
            self._repo.renumber()
        return changed

    def modify(self, tasks: Iterable[Task], changes: Changes) -> list[Task]:
        """Apply ``changes`` to ``tasks``; ``modified`` = now on the tasks that change.

        Returns:
            The changed tasks, as stored. Tasks the changes leave as they were are skipped.
        """
        now = self._clock()
        changed = [
            replace(new, modified=now) for task in tasks if (new := changes.apply(task)) != task
        ]
        if not changed:
            return []
        with self._repo.transaction():
            self._log(now, "modify", self._snapshot(changed))
            for task in changed:
                self._repo.update(task)
        return changed

    def import_tasks(self, tasks: Iterable[Task]) -> ImportResult:
        """Merge ``tasks`` by uuid: add new ones, update older ones, skip the others.

        A stored task is replaced only if the incoming ``modified`` is newer. New pending
        tasks get the next free short ids, in entry order; if an update changes which
        tasks are pending, all pending tasks are renumbered. One undo step.

        Returns:
            What was added, updated and skipped.
        """
        skipped: list[Task] = []
        before: dict[str, Task | None] = {}
        with self._repo.transaction():
            ids = self._repo.pending_ids()
            for task in tasks:
                current = self._repo.get(task.uuid)
                if current is not None and task.modified <= current.modified:
                    skipped.append(task)
                    continue
                before.setdefault(task.uuid, current)
                self._repo.restore(replace(task, id=current.id if current else None))
            if before:
                self._log(self._clock(), "import", list(before.items()), ids)
                self._number_imported(before)
            stored = {uuid: self._repo.get(uuid) for uuid in before}
        return ImportResult(
            added=tuple(t for u, t in stored.items() if t and before[u] is None),
            updated=tuple(t for u, t in stored.items() if t and before[u] is not None),
            skipped=tuple(skipped),
        )

    def _number_imported(self, before: Mapping[str, Task | None]) -> None:
        """Give short ids to imported tasks (see :meth:`import_tasks`)."""
        stored = [task for uuid in before if (task := self._repo.get(uuid)) is not None]
        if any(
            (old.status is Status.PENDING) != (task.status is Status.PENDING)
            for task in stored
            if (old := before[task.uuid]) is not None
        ):
            self._repo.renumber()
            return
        next_id = self._repo.max_pending_id()
        for task in sorted(stored, key=lambda task: task.entry):
            if task.status is Status.PENDING and task.id is None:
                next_id += 1
                self._repo.update(replace(task, id=next_id))

    def undo(self) -> UndoResult:
        """Revert the last write command (``add``, ``done``, ``delete``, ``modify``, ``import``).

        Each call goes one command further back. An undo cannot itself be undone.

        Returns:
            What was reverted.

        Raises:
            NoMatchError: If there is nothing to undo.
        """
        with self._repo.transaction():
            entry = self._repo.last_undo()
            if entry is None:
                raise NoMatchError("error.nothing_to_undo")
            restored: list[str] = []
            removed: list[Task] = []
            for uuid, task in entry.before:
                if task is None:
                    if (current := self._repo.get(uuid)) is not None:
                        removed.append(current)
                    self._repo.remove(uuid)
                else:
                    self._repo.restore(task)
                    restored.append(uuid)
            if entry.ids is not None:
                self._repo.set_ids(entry.ids)
            self._repo.drop_undo(entry.seq)
            tasks = tuple(task for uuid in restored if (task := self._repo.get(uuid)))
        return UndoResult(cmd=entry.cmd, restored=tasks, removed=tuple(removed))

    def _log(
        self,
        now: datetime,
        cmd: str,
        before: list[tuple[str, Task | None]],
        ids: dict[str, int] | None = None,
    ) -> None:
        """Log a write command for undo, and purge history past the retention."""
        self._repo.push_undo(now, cmd, before, ids)
        if self._undo_retention is not None:
            self._repo.prune_undo(now - self._undo_retention)

    def _snapshot(self, tasks: Iterable[Task]) -> list[tuple[str, Task | None]]:
        """Return the stored state of ``tasks``, for the undo log."""
        return [(task.uuid, self._repo.get(task.uuid)) for task in tasks]

    def state(self, key: str) -> str | None:
        """Return a small piece of app state (``meta`` table), or None if unset."""
        return self._repo.get_meta(key)

    def set_state(self, key: str, value: str) -> None:
        """Store a small piece of app state (``meta`` table); not part of undo."""
        self._repo.set_meta(key, value)

    def query(self, where: Filter | None = None) -> list[Task]:
        """Return the tasks matching ``where`` (default: all pending).

        Ordered by status (pending, completed, deleted), then short id, then entry.
        """
        where = where or Filter()
        return [
            task
            for status in where.statuses
            for task in self._repo.by_status(status)
            if where.matches(task)
        ]
