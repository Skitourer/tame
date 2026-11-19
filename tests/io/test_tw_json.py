import json
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from tame.core.models import Priority, Status, Task
from tame.errors import ValidationError
from tame.io.tw_json import (
    TW_STATUS,
    dumps,
    format_date,
    loads,
    parse_date,
    task_from_tw,
    task_to_tw,
)

NOW = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)
UUID = "a1b2c3d4-0000-4000-8000-000000000001"

# A task as Taskwarrior 3 exports it.
TW_TASK: dict[str, Any] = {
    "id": 3,
    "description": "Call bank",
    "due": "20261215T140000Z",
    "entry": "20261101T080000Z",
    "modified": "20261102T080000Z",
    "priority": "H",
    "project": "home.admin",
    "status": "pending",
    "tags": ["phone", "next"],
    "uuid": UUID,
    "annotations": [{"entry": "20261102T080000Z", "description": "ask for Ann"}],
    "urgency": 12.3,
}


def make_task(**fields: Any) -> Task:
    base: dict[str, Any] = {
        "uuid": UUID,
        "description": "x",
        "entry": NOW - timedelta(days=2),
        "modified": NOW - timedelta(days=1),
    }
    return Task(**(base | fields))


# --- Dates ---------------------------------------------------------------------------


def test_format_date_is_utc_basic_format() -> None:
    paris = timezone(timedelta(hours=1))
    assert format_date(datetime(2026, 12, 15, 15, 0, tzinfo=paris)) == "20261215T140000Z"


@pytest.mark.parametrize(
    "text",
    ["20261215T140000Z", "2026-12-15T14:00:00Z", "2026-12-15T15:00:00+01:00", "2026-12-15T14:00"],
)
def test_parse_date_forms(text: str) -> None:
    assert parse_date(text) == datetime(2026, 12, 15, 14, 0, tzinfo=UTC)


def test_parse_date_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_date("tomorrow")


# --- Export --------------------------------------------------------------------------


def test_task_to_tw_full() -> None:
    task = make_task(
        id=3,
        project="home",
        tags=frozenset({"b", "a"}),
        priority=Priority.H,
        due=datetime(2026, 12, 15, 14, 0, tzinfo=UTC),
        extra={"annotations": [{"description": "note"}]},
    )
    assert task_to_tw(task, urgency=12.34567) == {
        "id": 3,
        "description": "x",
        "due": "20261215T140000Z",
        "entry": "20261117T093000Z",
        "modified": "20261118T093000Z",
        "priority": "H",
        "project": "home",
        "status": "pending",
        "tags": ["a", "b"],
        "uuid": UUID,
        "urgency": 12.3457,
        "annotations": [{"description": "note"}],
    }


def test_task_to_tw_minimal_completed() -> None:
    data = task_to_tw(make_task(status=Status.COMPLETED, end=NOW))
    assert data == {
        "id": 0,
        "description": "x",
        "end": "20261119T093000Z",
        "entry": "20261117T093000Z",
        "modified": "20261118T093000Z",
        "status": "completed",
        "uuid": UUID,
    }


def test_task_to_tw_restores_tw_status_only_while_pending() -> None:
    waiting = make_task(extra={TW_STATUS: "waiting", "wait": "20261201T000000Z"})
    assert task_to_tw(waiting)["status"] == "waiting"
    assert TW_STATUS not in task_to_tw(waiting)
    done = make_task(status=Status.COMPLETED, extra={TW_STATUS: "waiting"})
    assert task_to_tw(done)["status"] == "completed"


def test_task_fields_win_over_extra() -> None:
    task = make_task(priority=Priority.L, extra={"priority": "Urgent"})
    assert task_to_tw(task)["priority"] == "L"
    assert task_to_tw(make_task(extra={"priority": "Urgent"}))["priority"] == "Urgent"


def test_dumps_one_task_per_line() -> None:
    assert dumps([]) == "[]"
    assert dumps([{"a": 1}, {"b": "é"}]) == '[\n{"a": 1},\n{"b": "é"}\n]'
    assert json.loads(dumps([{"a": 1}, {"b": 2}])) == [{"a": 1}, {"b": 2}]


# --- Import --------------------------------------------------------------------------


def test_loads_array_and_lines() -> None:
    assert loads('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]
    assert loads('{"a": 1}\n\n{"b": 2}\n') == [{"a": 1}, {"b": 2}]
    assert loads("  \n") == []


@pytest.mark.parametrize("text", ["[{", '{"a": 1} x', "[1, 2]", '"text"'])
def test_loads_rejects_invalid(text: str) -> None:
    with pytest.raises(ValidationError) as exc:
        loads(text)
    assert exc.value.key == "error.import_json"


def test_task_from_tw_full() -> None:
    task = task_from_tw(TW_TASK, NOW)
    assert task == Task(
        uuid=UUID,
        description="Call bank",
        entry=datetime(2026, 11, 1, 8, 0, tzinfo=UTC),
        modified=datetime(2026, 11, 2, 8, 0, tzinfo=UTC),
        status=Status.PENDING,
        project="home.admin",
        tags=frozenset({"phone", "next"}),
        priority=Priority.H,
        due=datetime(2026, 12, 15, 14, 0, tzinfo=UTC),
        extra={"annotations": TW_TASK["annotations"]},
    )


def test_task_from_tw_defaults() -> None:
    task = task_from_tw({"description": " Buy milk "}, NOW)
    assert uuid.UUID(task.uuid).version == 4
    assert (task.description, task.status, task.entry, task.modified) == (
        "Buy milk",
        Status.PENDING,
        NOW,
        NOW,
    )
    assert (task.id, task.project, task.tags, task.priority, task.extra) == (
        None,
        None,
        frozenset(),
        None,
        {},
    )


def test_task_from_tw_modified_defaults_to_entry() -> None:
    task = task_from_tw({"description": "x", "entry": "20261101T080000Z"}, NOW)
    assert task.modified == task.entry


@pytest.mark.parametrize("status", ["waiting", "recurring"])
def test_task_from_tw_pending_like_statuses(status: str) -> None:
    task = task_from_tw({"description": "x", "status": status, "recur": "weekly"}, NOW)
    assert task.status is Status.PENDING
    assert task.extra == {TW_STATUS: status, "recur": "weekly"}


def test_task_from_tw_keeps_other_priorities_in_extra() -> None:
    task = task_from_tw({"description": "x", "priority": "Urgent"}, NOW)
    assert (task.priority, task.extra) == (None, {"priority": "Urgent"})


def test_task_from_tw_normalizes_uuid() -> None:
    assert task_from_tw({"description": "x", "uuid": UUID.upper()}, NOW).uuid == UUID


@pytest.mark.parametrize(
    ("fields", "key"),
    [
        ({}, "error.empty_description"),
        ({"description": "  "}, "error.empty_description"),
        ({"description": 3}, "error.import_field"),
        ({"description": "x", "status": "zombie"}, "error.invalid_status"),
        ({"description": "x", "due": "soon"}, "error.invalid_date"),
        ({"description": "x", "tags": "a"}, "error.import_field"),
        ({"description": "x", "tags": ["a b"]}, "error.invalid_tag"),
        ({"description": "x", "project": "a..b"}, "error.invalid_project"),
        ({"description": "x", "uuid": "nope"}, "error.import_field"),
    ],
)
def test_task_from_tw_rejects_invalid(fields: dict[str, Any], key: str) -> None:
    with pytest.raises(ValidationError) as exc:
        task_from_tw(fields, NOW)
    assert exc.value.key == key


def test_round_trip() -> None:
    data = dict(TW_TASK)
    del data["urgency"]
    task = task_from_tw(data, NOW)
    exported = task_to_tw(task)
    assert exported == {**data, "id": 0, "tags": ["next", "phone"]}
    assert task_from_tw(exported, NOW) == task
