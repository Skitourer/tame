"""Task use cases. Returns objects and raises ``TameError``; never prints."""

import uuid as uuid_lib
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime

from tame.core.filters import Filter
from tame.core.models import (
    Task,
    check_description,
    check_project,
    check_tag,
    parse_priority,
)
from tame.storage.repo import TaskRepo

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """Return the current UTC time, truncated to the second (storage precision)."""
    return datetime.now(UTC).replace(microsecond=0)


class TaskService:
    """Entry point for task operations, shared by the CLI and a future TUI.

    Args:
        repo: Open task repository.
        clock: Returns the current aware datetime; injected for tests.
    """

    def __init__(self, repo: TaskRepo, clock: Clock = utc_now) -> None:
        self._repo = repo
        self._clock = clock

    def add(
        self,
        description: str,
        *,
        project: str | None = None,
        tags: Iterable[str] = (),
        priority: str | None = None,
    ) -> Task:
        """Create a pending task with the next free short id.

        Args:
            description: Task text; surrounding whitespace is stripped.
            project: Dotted project name.
            tags: Tag names, without leading ``+``.
            priority: H, M or L (any case).

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
        )
        with self._repo.transaction():
            task = replace(task, id=self._repo.max_pending_id() + 1)
            self._repo.insert(task)
        return task

    def query(self, where: Filter | None = None) -> list[Task]:
        """Return the tasks matching ``where`` (default: all pending), ordered by short id.

        Urgency sorting arrives in roadmap step 5.
        """
        where = where or Filter()
        return [
            task for task in self._repo.by_status(where.effective_status) if where.matches(task)
        ]
