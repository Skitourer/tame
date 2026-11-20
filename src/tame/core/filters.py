"""Task selection criteria, independent of any command-line syntax (SPEC §4)."""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Literal

from tame.core.dates import local_period
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
        virtual_in: Virtual tags the task must have (see :class:`VirtualTagger`).
        virtual_out: Virtual tags the task must not have.
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
    virtual_in: frozenset[str] = frozenset()
    virtual_out: frozenset[str] = frozenset()
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

    @property
    def uses_virtual_tags(self) -> bool:
        """True if matching needs the tasks' virtual tags."""
        return bool(self.virtual_in or self.virtual_out)

    def matches(self, task: Task, virtual: frozenset[str] = frozenset()) -> bool:
        """Return True if ``task`` meets every criterion.

        Args:
            task: The task.
            virtual: Its virtual tags; needed only if :attr:`uses_virtual_tags`.
        """
        return (
            self._selected(task)
            and task.status in self.statuses
            and self.tags_in <= task.tags
            and not self.tags_out & task.tags
            and self.virtual_in <= virtual
            and not self.virtual_out & virtual
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


DUE_SOON = timedelta(days=7)
"""How far ahead ``DUE`` looks."""


class VirtualTagger:
    """Computes the virtual tags of tasks (SPEC §4) at one point in time.

    Args:
        now: Current aware time.
        pending: Uuids of all pending tasks, for ``BLOCKED``/``UNBLOCKED``.
        tz: Local time zone for calendar periods; None means the system one.
    """

    def __init__(self, now: datetime, pending: Collection[str], tz: tzinfo | None = None) -> None:
        self._now = now
        self._pending = frozenset(pending)
        self._periods = {
            "TODAY": local_period("today", now, tz),
            "TOMORROW": local_period("tomorrow", now, tz),
            "WEEK": local_period("week", now, tz),
            "MONTH": local_period("month", now, tz),
        }

    def __call__(self, task: Task) -> frozenset[str]:
        """Return the virtual tags of ``task``."""
        tags: set[str] = set()
        if task.annotations:
            tags.add("ANNOTATED")
        if task.project:
            tags.add("PROJECT")
        if task.tags:
            tags.add("TAGGED")
        if task.status is not Status.PENDING:
            return frozenset(tags)
        tags.add("BLOCKED" if task.depends & self._pending else "UNBLOCKED")
        if (due := task.due) is not None:
            if due < self._now:
                tags.add("OVERDUE")
            if self._now <= due < self._now + DUE_SOON:
                tags.add("DUE")
            tags.update(name for name, (start, end) in self._periods.items() if start <= due < end)
        return frozenset(tags)
