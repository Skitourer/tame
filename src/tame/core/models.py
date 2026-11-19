"""Task domain model (SPEC §3). Field names follow Taskwarrior."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from tame.errors import ValidationError


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
    extra: dict[str, Any] = field(default_factory=dict)


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
