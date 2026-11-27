"""Task selection criteria, independent of any command-line syntax (SPEC §4)."""

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Literal

from tame.core.dates import local_period
from tame.core.models import NONE, Links, Priority, Status, Task
from tame.core.recurrence import same_period

ALL: Literal["all"] = "all"
"""Value of ``Filter.status`` matching every status (``status:all``)."""


class Condition(ABC):
    """A task selection: one :class:`Filter`, or filters combined with and/or/not.

    Status rule (SPEC §4): when no filter in the condition sets ``status``, only
    pending tasks match; otherwise each ``status`` is a plain condition and a filter
    without one matches any status.
    """

    __slots__ = ()

    @abstractmethod
    def leaves(self) -> Iterator["Filter"]:
        """Yield the filters this condition is made of."""

    @abstractmethod
    def holds(self, task: Task, virtual: frozenset[str]) -> bool:
        """True if ``task`` meets the condition, the default status aside."""

    @abstractmethod
    def _possible_statuses(self) -> frozenset[Status]:
        """The statuses a matching task can have (all of them if unconstrained)."""

    @property
    def has_status(self) -> bool:
        """True if some filter of the condition sets ``status``."""
        return any(leaf.status is not None for leaf in self.leaves())

    @property
    def statuses(self) -> tuple[Status, ...]:
        """The statuses to look at: pending by default (see the status rule)."""
        if not self.has_status:
            return (Status.PENDING,)
        possible = self._possible_statuses()
        return tuple(status for status in Status if status in possible)

    @property
    def shows_waiting(self) -> bool:
        """True if waiting tasks are not left out: ids/uuids, ``+WAITING`` or ``status:all``."""
        return any(
            leaf.ids or leaf.uuid_prefixes or "WAITING" in leaf.virtual_in or leaf.status == ALL
            for leaf in self.leaves()
        )

    @property
    def uses_virtual_tags(self) -> bool:
        """True if matching needs the tasks' virtual tags."""
        return any(leaf.virtual_in or leaf.virtual_out for leaf in self.leaves())

    def matches(self, task: Task, virtual: frozenset[str] = frozenset()) -> bool:
        """Return True if ``task`` meets the condition.

        Args:
            task: The task.
            virtual: Its virtual tags; needed only if :attr:`uses_virtual_tags`.
        """
        return task.status in self.statuses and self.holds(task, virtual)


@dataclass(frozen=True, slots=True)
class Not(Condition):
    """Tasks not meeting ``operand``."""

    operand: Condition

    def leaves(self) -> Iterator["Filter"]:  # noqa: D102
        yield from self.operand.leaves()

    def holds(self, task: Task, virtual: frozenset[str]) -> bool:  # noqa: D102
        return not self.operand.holds(task, virtual)

    def _possible_statuses(self) -> frozenset[Status]:
        return frozenset(Status)


@dataclass(frozen=True, slots=True)
class AllOf(Condition):
    """Tasks meeting every operand."""

    operands: tuple[Condition, ...]

    def leaves(self) -> Iterator["Filter"]:  # noqa: D102
        for operand in self.operands:
            yield from operand.leaves()

    def holds(self, task: Task, virtual: frozenset[str]) -> bool:  # noqa: D102
        return all(operand.holds(task, virtual) for operand in self.operands)

    def _possible_statuses(self) -> frozenset[Status]:
        possible = frozenset(Status)
        for operand in self.operands:
            possible &= operand._possible_statuses()
        return possible


@dataclass(frozen=True, slots=True)
class AnyOf(Condition):
    """Tasks meeting at least one operand."""

    operands: tuple[Condition, ...]

    def leaves(self) -> Iterator["Filter"]:  # noqa: D102
        for operand in self.operands:
            yield from operand.leaves()

    def holds(self, task: Task, virtual: frozenset[str]) -> bool:  # noqa: D102
        return any(operand.holds(task, virtual) for operand in self.operands)

    def _possible_statuses(self) -> frozenset[Status]:
        possible: frozenset[Status] = frozenset()
        for operand in self.operands:
            possible |= operand._possible_statuses()
        return possible


@dataclass(frozen=True, slots=True)
class Filter(Condition):
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
        recur: Recurrence period, compared by meaning (see :func:`same_period`);
            ``NONE`` for no recurrence.
        words: Case-insensitive substrings of the description.
        patterns: Regular expressions the description must match (searched anywhere).
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
    recur: str | None = None
    words: tuple[str, ...] = ()
    patterns: tuple[re.Pattern[str], ...] = ()

    def leaves(self) -> Iterator["Filter"]:  # noqa: D102
        yield self

    def _possible_statuses(self) -> frozenset[Status]:
        if self.status is None or self.status == ALL:
            return frozenset(Status)
        return frozenset({self.status})

    def holds(self, task: Task, virtual: frozenset[str]) -> bool:  # noqa: D102
        return (
            self._selected(task)
            and (self.status is None or self.status == ALL or task.status is self.status)
            and self.tags_in <= task.tags
            and not self.tags_out & task.tags
            and self.virtual_in <= virtual
            and not self.virtual_out & virtual
            and self._project_matches(task.project)
            and (self.priority is None or (task.priority or NONE) == self.priority)
            and (self.due_before is None or (task.due is not None and task.due < self.due_before))
            and (self.due_after is None or (task.due is not None and task.due > self.due_after))
            and (self.recur is None or same_period(task.recur, self.recur))
            and all(word.casefold() in task.description.casefold() for word in self.words)
            and all(pattern.search(task.description) for pattern in self.patterns)
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


def is_waiting(task: Task, now: datetime) -> bool:
    """True if ``task`` is pending with a ``wait`` date after ``now`` (SPEC §4)."""
    return task.status is Status.PENDING and task.wait is not None and task.wait > now


DUE_SOON = timedelta(days=7)
"""How far ahead ``DUE`` looks."""


class VirtualTagger:
    """Computes the virtual tags of tasks (SPEC §4) at one point in time.

    Args:
        now: Current aware time.
        links: Dependencies between pending tasks, for ``BLOCKED``/``UNBLOCKED``/``BLOCKING``.
        tz: Local time zone for calendar periods; None means the system one.
    """

    def __init__(self, now: datetime, links: Links, tz: tzinfo | None = None) -> None:
        self._now = now
        self._links = links
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
        tags.add("BLOCKED" if self._links.is_blocked(task) else "UNBLOCKED")
        if self._links.is_blocking(task):
            tags.add("BLOCKING")
        if task.start is not None:
            tags.add("ACTIVE")
        if task.recur:
            tags.add("RECURRING")
        if is_waiting(task, self._now):
            tags.add("WAITING")
        if (due := task.due) is not None:
            if due < self._now:
                tags.add("OVERDUE")
            if self._now <= due < self._now + DUE_SOON:
                tags.add("DUE")
            tags.update(name for name, (start, end) in self._periods.items() if start <= due < end)
        return frozenset(tags)
