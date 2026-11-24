"""Task domain model (SPEC §3). Field names follow Taskwarrior."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Literal

from tame.errors import ValidationError

NONE: Literal[""] = ""
"""Value of ``project``/``priority`` in filters and changes meaning "attribute not set"."""


class Status(StrEnum):
    """Task lifecycle status. ``deleted`` is a soft delete."""

    PENDING = "pending"
    COMPLETED = "completed"
    DELETED = "deleted"


class Priority(StrEnum):
    """Task priority."""

    H = "H"
    M = "M"
    L = "L"


@dataclass(frozen=True, slots=True)
class Annotation:
    """A timestamped note attached to a task.

    Attributes:
        entry: When the note was added.
        description: The note text.
    """

    entry: datetime
    description: str


@dataclass(frozen=True, slots=True)
class Session:
    """A finished stretch of work on a task, from ``start`` to ``stop`` (SPEC §5).

    Attributes:
        start: When work started.
        end: When it stopped.
    """

    start: datetime
    end: datetime

    @property
    def duration(self) -> timedelta:
        """How long it lasted."""
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class Task:
    """A task. Datetimes are timezone-aware (stored as UTC).

    Attributes:
        uuid: Permanent identifier (UUIDv4).
        description: Free text, never empty.
        entry: Creation time.
        modified: Last modification time.
        status: Lifecycle status.
        id: Short id; set for pending tasks only.
        project: Dotted project hierarchy, e.g. ``home.garden``.
        tags: Tag names, without leading ``+``.
        priority: H, M or L.
        due: Due date.
        end: Completion or deletion time.
        annotations: Notes, sorted by entry time.
        depends: Uuids of the tasks this one waits for (never its own).
        wait: Hidden from filters until then (SPEC §4 waiting tasks).
        start: When the current work session started (``tk start``); None if not active.
        recur: Recurrence period (SPEC §4 Recurrence); imported values stored as is.
        until: End of the recurrence.
        extra: Unknown Taskwarrior attributes, kept for JSON round-trip.
        sessions: Finished work sessions, by start time.
    """

    uuid: str
    description: str
    entry: datetime
    modified: datetime
    status: Status = Status.PENDING
    id: int | None = None
    project: str | None = None
    tags: frozenset[str] = frozenset()
    priority: Priority | None = None
    due: datetime | None = None
    end: datetime | None = None
    annotations: tuple[Annotation, ...] = ()
    depends: frozenset[str] = frozenset()
    wait: datetime | None = None
    start: datetime | None = None
    recur: str | None = None
    until: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    sessions: tuple[Session, ...] = ()

    @property
    def active(self) -> bool:
        """True if the task is pending and started."""
        return self.status is Status.PENDING and self.start is not None

    def time_spent(self, now: datetime) -> timedelta:
        """Total of the sessions, plus the current one if active."""
        total = sum((session.duration for session in self.sessions), timedelta())
        if self.start is not None and self.status is Status.PENDING:
            total += max(now - self.start, timedelta())
        return total


@dataclass(frozen=True, slots=True)
class TaskRefs:
    """Tasks named on the command line, before they are looked up.

    Attributes:
        ids: Short ids (pending tasks).
        uuid_prefixes: Uuid prefixes, lowercase, without dashes (any status).
    """

    ids: frozenset[int] = frozenset()
    uuid_prefixes: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        """Return True if at least one task is named."""
        return bool(self.ids or self.uuid_prefixes)


NO_REFS = TaskRefs()
"""No task named."""


@dataclass(frozen=True, slots=True)
class DependsChange:
    """A change of dependencies (``depends:3,-4`` / ``depends:``), Taskwarrior style.

    Attributes:
        add: Tasks to depend on, added to the current ones.
        remove: Tasks to depend on no more.
        clear: Drop every current dependency first.
    """

    add: TaskRefs = NO_REFS
    remove: TaskRefs = NO_REFS
    clear: bool = False


@dataclass(frozen=True, slots=True)
class Links:
    """Dependencies between pending tasks, for ``BLOCKED``/``BLOCKING`` and urgency.

    Attributes:
        ids: ``{uuid: short id}`` of every pending task.
        blocking: Uuids of the pending tasks that a pending task depends on.
    """

    ids: Mapping[str, int] = field(default_factory=dict)
    blocking: frozenset[str] = frozenset()

    def pending_depends(self, task: Task) -> list[str]:
        """Uuids of the pending tasks ``task`` depends on, by short id."""
        return sorted((uuid for uuid in task.depends if uuid in self.ids), key=self.ids.__getitem__)

    def is_blocked(self, task: Task) -> bool:
        """True if ``task`` is pending and depends on a pending task."""
        return task.status is Status.PENDING and any(uuid in self.ids for uuid in task.depends)

    def is_blocking(self, task: Task) -> bool:
        """True if ``task`` is pending and a pending task depends on it."""
        return task.status is Status.PENDING and task.uuid in self.blocking


@dataclass(frozen=True, slots=True)
class Changes:
    """Modifications to apply to tasks (``modify``), independent of any command-line syntax.

    Attributes:
        description: New description; None keeps it.
        project: New project; ``NONE`` clears it; None keeps it.
        priority: New priority; ``NONE`` clears it; None keeps it.
        due: New due date; ``NONE`` clears it; None keeps it.
        wait: New wait date; ``NONE`` clears it; None keeps it.
        recur: New recurrence period (checked); ``NONE`` ends the series; None keeps it.
        until: New end of the recurrence; ``NONE`` clears it; None keeps it.
        tags_add: Tags to add.
        tags_remove: Tags to remove.
        depends: Dependency change, resolved by the service; None keeps them.
    """

    description: str | None = None
    project: str | None = None
    priority: Priority | Literal[""] | None = None
    due: datetime | Literal[""] | None = None
    wait: datetime | Literal[""] | None = None
    tags_add: frozenset[str] = frozenset()
    tags_remove: frozenset[str] = frozenset()
    depends: DependsChange | None = None
    recur: str | None = None
    until: datetime | Literal[""] | None = None

    def __bool__(self) -> bool:
        """Return True if at least one change is requested."""
        return any(
            (
                self.description is not None,
                self.project is not None,
                self.priority is not None,
                self.due is not None,
                self.wait is not None,
                self.tags_add,
                self.tags_remove,
                self.depends is not None,
                self.recur is not None,
                self.until is not None,
            )
        )

    def apply(self, task: Task) -> Task:
        """Return ``task`` with the changes applied; ``modified`` is left untouched.

        ``depends`` is not applied here: it needs the other tasks (see the service).
        """
        return replace(
            task,
            description=task.description if self.description is None else self.description,
            project=task.project if self.project is None else self.project or None,
            priority=task.priority if self.priority is None else self.priority or None,
            due=task.due if self.due is None else self.due or None,
            wait=task.wait if self.wait is None else self.wait or None,
            recur=task.recur if self.recur is None else self.recur or None,
            until=task.until if self.until is None else self.until or None,
            tags=(task.tags | self.tags_add) - self.tags_remove,
        )


def check_description(description: str) -> str:
    """Return the stripped description.

    Raises:
        ValidationError: If the description is blank.
    """
    description = description.strip()
    if not description:
        raise ValidationError("error.empty_description")
    return description


def check_tag(tag: str) -> str:
    """Return ``tag`` if valid: non-empty, no whitespace, no leading ``+``/``-``.

    Raises:
        ValidationError: If the tag is invalid.
    """
    if not tag or tag[0] in "+-" or any(c.isspace() for c in tag):
        raise ValidationError("error.invalid_tag", tag=tag)
    return tag


VIRTUAL_TAGS = frozenset(
    {
        "OVERDUE",
        "TODAY",
        "TOMORROW",
        "WEEK",
        "MONTH",
        "DUE",
        "BLOCKED",
        "UNBLOCKED",
        "BLOCKING",
        "ACTIVE",
        "RECURRING",
        "WAITING",
        "ANNOTATED",
        "PROJECT",
        "TAGGED",
    }
)
"""Tags computed when filtering (SPEC §4); reserved: they cannot be set."""


def check_new_tag(tag: str) -> str:
    """Return ``tag`` if it is valid and may be set on a task (not a virtual tag).

    Raises:
        ValidationError: If the tag is invalid or a virtual tag.
    """
    if check_tag(tag) in VIRTUAL_TAGS:
        raise ValidationError("error.virtual_tag", tag=tag)
    return tag


def check_project(project: str) -> str:
    """Return ``project`` if valid: dotted names, no empty segment, no whitespace.

    Raises:
        ValidationError: If the project is invalid.
    """
    if any(not part for part in project.split(".")) or any(c.isspace() for c in project):
        raise ValidationError("error.invalid_project", project=project)
    return project


def parse_priority(value: str) -> Priority:
    """Parse a priority, case-insensitively.

    Raises:
        ValidationError: If ``value`` is not H, M or L.
    """
    try:
        return Priority(value.upper())
    except ValueError:
        raise ValidationError("error.invalid_priority", value=value) from None
