"""Task domain model (SPEC §3). Field names follow Taskwarrior."""

from dataclasses import dataclass, field, replace
from datetime import datetime
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
        start: When work started (used from 0.4).
        recur: Taskwarrior recurrence period, stored as is (used from 0.4).
        until: End of the recurrence (used from 0.4).
        extra: Unknown Taskwarrior attributes, kept for JSON round-trip.
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


@dataclass(frozen=True, slots=True)
class Changes:
    """Modifications to apply to tasks (``modify``), independent of any command-line syntax.

    Attributes:
        description: New description; None keeps it.
        project: New project; ``NONE`` clears it; None keeps it.
        priority: New priority; ``NONE`` clears it; None keeps it.
        due: New due date; ``NONE`` clears it; None keeps it.
        wait: New wait date; ``NONE`` clears it; None keeps it.
        tags_add: Tags to add.
        tags_remove: Tags to remove.
    """

    description: str | None = None
    project: str | None = None
    priority: Priority | Literal[""] | None = None
    due: datetime | Literal[""] | None = None
    wait: datetime | Literal[""] | None = None
    tags_add: frozenset[str] = frozenset()
    tags_remove: frozenset[str] = frozenset()

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
            )
        )

    def apply(self, task: Task) -> Task:
        """Return ``task`` with the changes applied; ``modified`` is left untouched."""
        return replace(
            task,
            description=task.description if self.description is None else self.description,
            project=task.project if self.project is None else self.project or None,
            priority=task.priority if self.priority is None else self.priority or None,
            due=task.due if self.due is None else self.due or None,
            wait=task.wait if self.wait is None else self.wait or None,
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
