"""Task selection criteria, independent of any command-line syntax (SPEC §4)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from tame.core.models import NONE, Priority, Status, Task

ALL: Literal["all"] = "all"
"""Value of ``Filter.status`` matching every status (``status:all``)."""


@dataclass(frozen=True, slots=True)
class Filter:
    """Criteria a task must meet. All set criteria are AND-combined.

    Ids and uuid prefixes together form one selection: a task matches it if it
    has one of the ids *or* one of the uuid prefixes.

    Attributes:
        ids: Short ids.
        uuid_prefixes: Lowercase hex uuid prefixes, dashes ignored.
        tags_in: Tags the task must have.
        tags_out: Tags the task must not have.
        project: Project name, matching itself and its sub-projects; ``NONE`` for no project.
        priority: Exact priority; ``NONE`` for no priority.
        status: Exact status; ``ALL`` for any status; None means pending.
        due_before: The task is due strictly before this time.
        due_after: The task is due strictly after this time.
        words: Case-insensitive substrings of the description.
    """

    ids: frozenset[int] = frozenset()
    uuid_prefixes: tuple[str, ...] = ()
    tags_in: frozenset[str] = frozenset()
    tags_out: frozenset[str] = frozenset()
    project: str | None = None
    priority: Priority | Literal[""] | None = None
    status: Status | Literal["all"] | None = None
    due_before: datetime | None = None
    due_after: datetime | None = None
    words: tuple[str, ...] = ()

    @property
    def statuses(self) -> tuple[Status, ...]:
        """The statuses to match: ``status``, all of them, or pending by default."""
        if self.status == ALL:
            return tuple(Status)
        return (self.status or Status.PENDING,)

    def matches(self, task: Task) -> bool:
        """Return True if ``task`` meets every criterion."""
        return (
            self._selected(task)
            and task.status in self.statuses
            and self.tags_in <= task.tags
            and not self.tags_out & task.tags
            and self._project_matches(task.project)
            and (self.priority is None or (task.priority or NONE) == self.priority)
            and (self.due_before is None or (task.due is not None and task.due < self.due_before))
            and (self.due_after is None or (task.due is not None and task.due > self.due_after))
            and all(word.casefold() in task.description.casefold() for word in self.words)
        )

    def _selected(self, task: Task) -> bool:
        if not self.ids and not self.uuid_prefixes:
            return True
        compact = task.uuid.replace("-", "")
        return task.id in self.ids or any(compact.startswith(p) for p in self.uuid_prefixes)

    def _project_matches(self, project: str | None) -> bool:
        if self.project is None:
            return True
        if self.project == NONE:
            return project is None
        return project is not None and (
            project == self.project or project.startswith(self.project + ".")
        )
