"""Taskwarrior JSON import/export format (SPEC §7).

Export: a JSON array, Taskwarrior field names, dates as ``YYYYMMDDTHHMMSSZ``, the
``extra`` attributes merged back. Import: a JSON array, or one object per line.
Annotations and dependencies are stored natively when valid. Attributes TAME does not
support (recur, wait, UDAs...) and invalid annotations/dependencies go to ``extra`` and
come back unchanged on export. Taskwarrior statuses ``waiting`` and
``recurring`` become ``pending``; the original is kept in ``extra["tw_status"]``.
"""

import json
import uuid as uuid_lib
from collections.abc import Collection, Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from tame.core.models import (
    Annotation,
    Priority,
    Status,
    Task,
    check_description,
    check_project,
    check_tag,
)
from tame.errors import ValidationError

TW_STATUS = "tw_status"
"""``extra`` key holding a Taskwarrior status TAME maps to ``pending``."""

ANNOTATIONS = "annotations"
DEPENDS = "depends"
_EXTRA_DATES = ("wait", "start", "until")
"""Taskwarrior dates TAME stores natively since schema 3."""
PROMOTABLE = (ANNOTATIONS, DEPENDS, *_EXTRA_DATES, "recur")
"""Task fields :func:`split_extra` can take out of ``extra``."""

_PENDING_LIKE = frozenset({"waiting", "recurring"})
_DATE_FIELDS = ("due", "end", "entry", "modified")
_IGNORED = frozenset({"id", "urgency"})
"""Computed by Taskwarrior and TAME alike: never imported."""
_KNOWN = frozenset({"uuid", "description", "status", "project", "tags", "priority"}).union(
    _DATE_FIELDS, _IGNORED
)


def format_date(value: datetime) -> str:
    """Format an aware datetime as Taskwarrior does, e.g. ``20261215T140000Z``."""
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def parse_date(value: str) -> datetime:
    """Parse a Taskwarrior date (``20261215T140000Z``) or an ISO 8601 one.

    A date without offset is taken as UTC.

    Raises:
        ValueError: If ``value`` is not a date.
    """
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC).replace(microsecond=0)


def task_to_tw(task: Task, urgency: float | None = None) -> dict[str, Any]:
    """Return ``task`` as a Taskwarrior JSON object.

    Args:
        task: The task.
        urgency: Its urgency, exported for information (ignored on import).
    """
    data: dict[str, Any] = {"id": task.id or 0, "description": task.description}
    for name in _DATE_FIELDS:
        if (value := getattr(task, name)) is not None:
            data[name] = format_date(value)
    if task.priority:
        data["priority"] = task.priority.value
    if task.project:
        data["project"] = task.project
    extra = dict(task.extra)
    tw_status = extra.pop(TW_STATUS, None)
    data["status"] = tw_status if task.status is Status.PENDING and tw_status else task.status
    if task.tags:
        data["tags"] = sorted(task.tags)
    if task.annotations:
        data[ANNOTATIONS] = [
            {"entry": format_date(note.entry), "description": note.description}
            for note in sorted(task.annotations, key=lambda note: note.entry)
        ]
    if task.depends:
        data[DEPENDS] = sorted(task.depends)
    for name in _EXTRA_DATES:
        if (value := getattr(task, name)) is not None:
            data[name] = format_date(value)
    if task.recur:
        data["recur"] = task.recur
    data["uuid"] = task.uuid
    if urgency is not None:
        data["urgency"] = round(urgency, 4)
    return {**extra, **data}


def dumps(objects: Iterable[Mapping[str, Any]]) -> str:
    """Return ``objects`` as a JSON array with one object per line, like Taskwarrior."""
    lines = [json.dumps(obj, ensure_ascii=False) for obj in objects]
    return "[\n" + ",\n".join(lines) + "\n]" if lines else "[]"


def loads(text: str) -> list[dict[str, Any]]:
    """Parse a JSON array of objects, or one object per line (blank lines skipped).

    Raises:
        ValidationError: If the text is not valid JSON or holds something else than
            objects.
    """
    stripped = text.strip()
    if not stripped:
        return []
    try:
        if stripped.startswith("["):
            items = json.loads(stripped)
        else:
            items = [json.loads(line) for line in stripped.splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise ValidationError("error.import_json", detail=str(exc)) from None
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ValidationError("error.import_json", detail="expected JSON objects")
    return items


def task_from_tw(data: Mapping[str, Any], now: datetime) -> Task:
    """Build a task from a Taskwarrior JSON object.

    Missing ``uuid`` → a new one; missing ``entry`` → ``now``; missing ``modified`` →
    ``entry``; missing ``status`` → pending. A priority other than H/M/L is kept in
    ``extra``, as are unknown attributes. The short id is not set.

    Raises:
        ValidationError: If a field has a wrong type or an invalid value.
    """
    uuid = _uuid(data)
    fields, extra = split_extra(
        {key: value for key, value in data.items() if key not in _KNOWN}, uuid
    )
    dates = {name: _date(data, name) for name in _DATE_FIELDS}
    entry = dates["entry"] or now
    status_text = _str(data, "status") or Status.PENDING.value
    if status_text in _PENDING_LIKE:
        if not (status_text == "waiting" and "wait" in fields):  # TW 3 style: pending + wait
            extra[TW_STATUS] = status_text
        status_text = Status.PENDING.value
    try:
        status = Status(status_text)
    except ValueError:
        raise ValidationError("error.invalid_status", value=status_text) from None
    priority: Priority | None = None
    if (priority_text := _str(data, "priority")) is not None:
        if priority_text in Priority.__members__:
            priority = Priority(priority_text)
        else:
            extra["priority"] = priority_text
    tags = data.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise _field_error("tags", tags)
    project = _str(data, "project")
    return Task(
        uuid=uuid,
        description=check_description(_str(data, "description") or ""),
        entry=entry,
        modified=dates["modified"] or entry,
        status=status,
        project=check_project(project) if project else None,
        tags=frozenset(check_tag(tag) for tag in tags),
        priority=priority,
        due=dates["due"],
        end=dates["end"],
        extra=extra,
        **fields,
    )


def split_extra(
    extra: Mapping[str, Any], uuid: str, names: Collection[str] = PROMOTABLE
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Take the valid Taskwarrior attributes TAME stores natively out of ``extra``.

    ``annotations``: a list of ``{entry, description}`` (both strings, ``entry`` a date),
    sorted by entry. ``depends``: a list of uuids, or a comma-separated string
    (Taskwarrior < 2.6); duplicates and ``uuid`` itself are dropped. ``wait``, ``start``,
    ``until``: dates. ``recur``: a non-empty string. A key with an invalid value stays in
    the remaining attributes unchanged. Once ``wait`` is taken, ``tw_status = "waiting"``
    is dropped (Taskwarrior 3 style: pending + wait).

    Args:
        extra: Attributes TAME stores as is.
        uuid: Uuid of the task they belong to.
        names: Which of :data:`PROMOTABLE` to take (migrations take a fixed set).

    Returns:
        The taken values by :class:`Task` field name, and the other attributes.
    """
    rest = dict(extra)
    fields: dict[str, Any] = {}
    notes = _annotations(rest[ANNOTATIONS]) if ANNOTATIONS in rest else None
    if ANNOTATIONS in names and notes is not None:
        fields[ANNOTATIONS] = notes
        del rest[ANNOTATIONS]
    uuids = _depends(rest[DEPENDS]) if DEPENDS in rest else None
    if DEPENDS in names and uuids is not None:
        fields[DEPENDS] = uuids - {uuid}
        del rest[DEPENDS]
    for name in _EXTRA_DATES:
        if name in names and isinstance(value := rest.get(name), str):
            try:
                fields[name] = parse_date(value)
            except ValueError:
                continue
            del rest[name]
    if "recur" in names and isinstance(recur := rest.get("recur"), str) and recur:
        fields["recur"] = recur
        del rest["recur"]
    if "wait" in fields and rest.get(TW_STATUS) == "waiting":
        del rest[TW_STATUS]
    return fields, rest


def _annotations(value: object) -> tuple[Annotation, ...] | None:
    """Parse Taskwarrior annotations; None if anything is invalid."""
    if not isinstance(value, list):
        return None
    notes = []
    for item in value:
        if not isinstance(item, dict):
            return None
        entry, description = item.get("entry"), item.get("description")
        if not isinstance(entry, str) or not isinstance(description, str):
            return None
        try:
            notes.append(Annotation(parse_date(entry), description))
        except ValueError:
            return None
    return tuple(sorted(notes, key=lambda note: note.entry))


def _depends(value: object) -> frozenset[str] | None:
    """Parse Taskwarrior dependencies; None if anything is invalid."""
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    try:
        return frozenset(str(uuid_lib.UUID(item)) for item in value)
    except ValueError:
        return None


def _str(data: Mapping[str, Any], name: str) -> str | None:
    value = data.get(name)
    if value is not None and not isinstance(value, str):
        raise _field_error(name, value)
    return value


def _date(data: Mapping[str, Any], name: str) -> datetime | None:
    if (text := _str(data, name)) is None:
        return None
    try:
        return parse_date(text)
    except ValueError:
        raise ValidationError("error.invalid_date", value=text) from None


def _uuid(data: Mapping[str, Any]) -> str:
    if (text := _str(data, "uuid")) is None:
        return str(uuid_lib.uuid4())
    try:
        return str(uuid_lib.UUID(text))
    except ValueError:
        raise _field_error("uuid", text) from None


def _field_error(name: str, value: object) -> ValidationError:
    return ValidationError("error.import_field", name=name, value=json.dumps(value))
