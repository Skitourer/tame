"""Recurrence on the command line, and Taskwarrior series on import (SPEC §4, §5, §7)."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tame.__main__ import main
from tame.cli.parser import parse_add, parse_filter, parse_modify
from tame.core.models import NONE, Status, Task
from tame.core.recurrence import ANCHOR
from tame.errors import ValidationError
from tame.io.tw_json import PARENT, TW_STATUS, convert_recurring

Capture = pytest.CaptureFixture[str]
NOW = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)


def run(capsys: Capture, *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def export(capsys: Capture) -> list[dict[str, object]]:
    return [json.loads(line.rstrip(",")) for line in run(capsys, "export")[1].splitlines()[1:-1]]


# --- Parsing -------------------------------------------------------------------------


def test_add_and_modify_take_recur_and_until() -> None:
    added = parse_add(["Backup", "due:2027-01-08", "recur:Weekly", "until:2027-12-31"], NOW)
    assert (added.recur, added.until is not None) == ("weekly", True)
    changes = parse_modify(["recur:2w", "until:"], NOW)
    assert (changes.recur, changes.until) == ("2w", NONE)
    assert parse_modify(["recur:"], NOW).recur == NONE


def test_unknown_period_is_refused() -> None:
    for parse in (parse_add, parse_modify):
        with pytest.raises(ValidationError) as exc:
            parse(["x", "recur:fortnight"], NOW)
        assert exc.value.key == "error.invalid_recur"


def test_recur_filter_keeps_the_value_as_typed() -> None:
    assert parse_filter(["recur:P1W"], NOW).recur == "P1W"
    assert parse_filter(["recur:"], NOW).recur == NONE


# --- Commands ------------------------------------------------------------------------


def test_done_announces_the_next_task(capsys: Capture) -> None:
    run(capsys, "add", "Paint")
    assert run(capsys, "add", "Backup", "due:2020-01-03", "recur:weekly")[0] == 0
    code, out, _ = run(capsys, "2", "done")
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "Completed task 2 'Backup'."
    assert lines[1].startswith("Next: task 2 'Backup', due ")
    (task,) = [item for item in export(capsys) if item["description"] == "Backup"]
    assert task["recur"] == "weekly"


def test_last_of_its_series(capsys: Capture) -> None:
    run(capsys, "add", "Backup", "due:2020-01-03", "recur:weekly", "until:2020-02-01")
    out = run(capsys, "1", "done")[1]
    assert out.splitlines()[1] == "Task 1 'Backup' was the last of its series."
    assert run(capsys, "list")[0] == 2


def test_unknown_imported_period_warns(capsys: Capture, tmp_path: Path) -> None:
    data = {"uuid": "a1b2c3d4-0000-4000-8000-000000000001", "description": "Odd"}
    data |= {"status": "pending", "due": "20270108T120000Z", "recur": "P1W"}
    path = tmp_path / "in.json"
    path.write_text(json.dumps([data]), encoding="utf-8")
    run(capsys, "import", str(path))
    code, out, err = run(capsys, "1", "done")
    assert code == 0
    assert out.splitlines() == ["Completed task 1 'Odd'."]
    assert err.strip() == "Task 1 'Odd': recurrence 'P1W' not understood, no next task."


def test_rules_give_validation_errors(capsys: Capture) -> None:
    assert run(capsys, "add", "Backup", "recur:weekly")[2].strip() == (
        "A recurring task needs a due date: add due:DATE (recur: ends the series)."
    )
    assert run(capsys, "add", "Backup", "due:fri", "until:eoy")[0] == 1
    run(capsys, "add", "Backup", "due:fri", "recur:weekly")
    assert run(capsys, "1", "modify", "due:")[0] == 1
    assert run(capsys, "1", "modify", "due:", "recur:")[0] == 0


def test_list_shows_the_period_and_filters_on_it(capsys: Capture) -> None:
    run(capsys, "add", "Backup", "due:fri", "recur:biweekly")
    run(capsys, "add", "Plain")
    out = run(capsys, "list")[1]
    assert "Recur" in out.splitlines()[0]
    assert "biweekly" in out
    assert "Recur" not in run(capsys, "2", "list")[1]  # Hidden when empty.
    assert "Recur" in run(capsys, "next")[1]
    assert "Backup" in run(capsys, "recur:2w", "list")[1]
    assert "Plain" not in run(capsys, "+RECURRING", "list")[1]
    assert "Backup" not in run(capsys, "-RECURRING", "list")[1]
    assert run(capsys, "1", "modify", "+RECURRING")[0] == 1  # Reserved.


def test_info_shows_recurrence_and_until(capsys: Capture) -> None:
    run(capsys, "add", "Backup", "due:fri", "recur:weekly", "until:2099-12-31")
    out = run(capsys, "1", "info")[1]
    assert "Recurrence  weekly" in out
    assert "Until" in out
    run(capsys, "add", "Rent", "due:2099-01-31", "recur:monthly")
    assert "recur_anchor" not in run(capsys, "2", "info")[1]  # Kept in extra, not shown.


def test_undo_of_done_reopens_and_removes(capsys: Capture) -> None:
    run(capsys, "add", "Backup", "due:2020-01-03", "recur:weekly")
    run(capsys, "1", "done")
    out = run(capsys, "undo")[1]
    assert "Removed task" in out
    assert "Restored task 1 'Backup'." in out
    assert [item["status"] for item in export(capsys)] == ["pending"]


# --- Taskwarrior series --------------------------------------------------------------


def tw_task(uuid: str, status: Status = Status.PENDING, **attrs: object) -> Task:
    """A task as :func:`task_from_tw` makes it; ``template=True`` for a TW template."""
    extra = {TW_STATUS: "recurring"} if attrs.pop("template", False) else {}
    if "parent" in attrs:
        extra[PARENT] = str(attrs.pop("parent"))
    if "imask" in attrs:
        extra["imask"] = attrs.pop("imask")  # type: ignore[assignment]
    task = Task(uuid=uuid, description="Backup", entry=NOW, modified=NOW, status=status)
    return replace(task, extra=extra, **attrs)  # type: ignore[arg-type]


JAN31, FEB28 = datetime(2027, 1, 31, 12, tzinfo=UTC), datetime(2027, 2, 28, 12, tzinfo=UTC)


def test_template_goes_to_the_nearest_pending_instance() -> None:
    template = tw_task("t", template=True, due=JAN31, recur="monthly", until=FEB28)
    later = tw_task("b", parent="t", imask=2, due=FEB28, recur="monthly")
    done = tw_task("c", Status.COMPLETED, parent="t")
    nearest = tw_task("a", parent="t", imask=1, due=JAN31, recur="monthly")
    tasks, converted = convert_recurring([template, later, done, nearest], [], NOW)
    by_uuid = {task.uuid: task for task in tasks}
    assert converted == 1
    assert set(by_uuid) == {"a", "b", "c"}
    assert (by_uuid["a"].recur, by_uuid["a"].until) == ("monthly", FEB28)
    assert by_uuid["a"].extra == {PARENT: "t", "imask": 1, ANCHOR: 31}
    assert (by_uuid["b"].recur, by_uuid["b"].until) == (None, None)
    assert by_uuid["b"].extra == {PARENT: "t", "imask": 2}
    assert by_uuid["c"] == done


def test_template_without_pending_instance_becomes_one() -> None:
    monday = datetime(2026, 1, 5, 12, tzinfo=UTC)
    template = tw_task("t", template=True, due=monday, recur="weekly")
    (task,), converted = convert_recurring([template], [], NOW)
    assert converted == 1
    assert task.uuid != "t"
    assert (task.recur, task.status, task.entry) == ("weekly", Status.PENDING, NOW)
    assert task.due is not None
    assert NOW < task.due < NOW + timedelta(days=8)
    assert (task.due - monday) % timedelta(days=7) == timedelta()  # Mondays, as the template.
    assert task.extra == {PARENT: "t"}


def test_stored_instance_takes_the_series() -> None:
    monday = datetime(2027, 1, 4, tzinfo=UTC)
    stored = tw_task("s", parent="t", due=monday)
    template = tw_task("t", template=True, due=monday, recur="weekly")
    tasks, _ = convert_recurring([template], [stored], NOW)
    assert [(task.uuid, task.recur, task.modified) for task in tasks] == [("s", "weekly", NOW)]


def test_without_template_nothing_changes() -> None:
    tasks = [tw_task("a", parent="t", due=JAN31, recur="weekly")]
    assert convert_recurring(tasks, [], NOW) == (tasks, 0)


def test_import_converts_and_says_so(capsys: Capture, tmp_path: Path) -> None:
    items = [
        {"uuid": "11111111-0000-4000-8000-000000000000", "description": "Backup"}
        | {"status": "recurring", "due": "20260105T120000Z", "recur": "weekly", "mask": "--"},
        {"uuid": "22222222-0000-4000-8000-000000000000", "description": "Backup"}
        | {"status": "pending", "due": "20990105T120000Z", "recur": "weekly"}
        | {"parent": "11111111-0000-4000-8000-000000000000", "imask": 1},
    ]
    path = tmp_path / "in.json"
    path.write_text(json.dumps(items), encoding="utf-8")
    out = run(capsys, "import", str(path))[1]
    assert out.splitlines() == [
        "Imported: 1 added, 0 updated, 0 skipped (not newer).",
        "Recurring series converted from Taskwarrior templates: 1.",
    ]
    (task,) = export(capsys)
    assert (task["uuid"], task["recur"], task["status"]) == (items[1]["uuid"], "weekly", "pending")
