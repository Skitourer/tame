"""Dependencies: ``depends:`` in ``add``/``modify`` and what they change (SPEC §4, §5, §6)."""

import json
import re

import pytest

from tame.__main__ import main
from tame.cli.parser import parse_add, parse_depends, parse_modify
from tame.core.models import DependsChange, TaskRefs
from tame.errors import ValidationError

Capture = pytest.CaptureFixture[str]


def run(capsys: Capture, *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def export(capsys: Capture) -> dict[str, dict[str, object]]:
    """Tasks by description."""
    return {
        task["description"]: task for task in json.loads(run(capsys, "status:all", "export")[1])
    }


@pytest.fixture
def five(capsys: Capture) -> None:
    for name in ("one", "two", "three", "four", "five"):
        run(capsys, "add", name)


# --- Parsing -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", DependsChange(clear=True)),
        ("3,4", DependsChange(add=TaskRefs(frozenset({3, 4})))),
        ("1-3", DependsChange(add=TaskRefs(frozenset({1, 2, 3})))),
        ("-3", DependsChange(remove=TaskRefs(frozenset({3})))),
        ("5,-3", DependsChange(add=TaskRefs(frozenset({5})), remove=TaskRefs(frozenset({3})))),
        (
            "1A2B3C4D,-a1b2c3d4-0000",
            DependsChange(
                add=TaskRefs(uuid_prefixes=("1a2b3c4d",)),
                remove=TaskRefs(uuid_prefixes=("a1b2c3d40000",)),
            ),
        ),
        # A uuid made of digits only: dashed, it is never read as an id range.
        ("12345678-1234", DependsChange(add=TaskRefs(uuid_prefixes=("123456781234",)))),
        ("-12345678-9", DependsChange(remove=TaskRefs(uuid_prefixes=("123456789",)))),
    ],
)
def test_parse_depends(value: str, expected: DependsChange) -> None:
    assert parse_depends(value) == expected


@pytest.mark.parametrize("value", ["x", "3,", "abc", "--3", "1a2b"])
def test_parse_depends_rejects_what_names_no_task(value: str) -> None:
    with pytest.raises(ValidationError) as exc:
        parse_depends(value)
    assert exc.value.key == "error.invalid_depends"


def test_depends_tokens_combine_in_order() -> None:
    changes = parse_modify(["depends:3", "depends:-4,5"])
    assert changes.depends == DependsChange(
        add=TaskRefs(frozenset({3, 5})), remove=TaskRefs(frozenset({4}))
    )
    assert parse_modify(["depends:3", "depends:"]).depends == DependsChange(clear=True)


def test_add_takes_additions_only() -> None:
    assert parse_add(["x", "depends:2,3"]).depends == TaskRefs(frozenset({2, 3}))
    with pytest.raises(ValidationError):
        parse_add(["x", "depends:-2"])


# --- modify ----------------------------------------------------------------------------


@pytest.mark.usefixtures("five")
def test_spec_example_adds_like_taskwarrior(capsys: Capture) -> None:
    assert run(capsys, "5", "modify", "depends:3,4")[0] == 0
    run(capsys, "5", "modify", "depends:1")
    tasks = export(capsys)
    wanted = {tasks[name]["uuid"] for name in ("one", "three", "four")}
    assert set(tasks["five"]["depends"]) == wanted  # type: ignore[arg-type]
    run(capsys, "5", "modify", "depends:-3")
    assert len(export(capsys)["five"]["depends"]) == 2  # type: ignore[arg-type]
    run(capsys, "5", "modify", "depends:")
    assert "depends" not in export(capsys)["five"]


@pytest.mark.usefixtures("five")
def test_undo_restores_dependencies(capsys: Capture) -> None:
    run(capsys, "5", "modify", "depends:3")
    run(capsys, "undo")
    assert "depends" not in export(capsys)["five"]


@pytest.mark.usefixtures("five")
@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["5", "modify", "depends:9"], "No task 9.\n"),
        (["5", "modify", "depends:5"], "Task 5 cannot depend on itself.\n"),
        (["5", "modify", "depends:x"], "Invalid dependency: 'x'"),
        (["5", "modify", "depends:ffffffff"], "No task ffffffff.\n"),
    ],
)
def test_errors_change_nothing(capsys: Capture, argv: list[str], message: str) -> None:
    code, _, err = run(capsys, *argv)
    assert code == 1
    assert err.startswith(message)
    assert "depends" not in export(capsys)["five"]


@pytest.mark.usefixtures("five")
def test_cycle_is_refused_with_its_chain(capsys: Capture) -> None:
    run(capsys, "5", "modify", "depends:3")
    run(capsys, "3", "modify", "depends:2")
    code, _, err = run(capsys, "2", "modify", "depends:5")
    assert code == 1
    assert err == "Dependency cycle: 2 → 5 → 3 → 2\n"
    assert "depends" not in export(capsys)["two"]


@pytest.mark.usefixtures("five")
def test_by_uuid_prefix_any_status(capsys: Capture) -> None:
    run(capsys, "1", "done")
    done = export(capsys)["one"]["uuid"]
    assert isinstance(done, str)
    assert run(capsys, "4", "modify", f"depends:{done[:13]}")[0] == 0  # dashed: never an id
    assert export(capsys)["five"]["depends"] == [done]
    assert re.search(r"\bBLOCKED\b", run(capsys, "4", "info")[1]) is None


# --- add, list, next, done, info ----------------------------------------------------


@pytest.mark.usefixtures("five")
def test_add_with_depends_and_list_dep_column(capsys: Capture) -> None:
    run(capsys, "add", "Paint walls", "depends:2,3")
    out = run(capsys, "list")[1]
    header = out.splitlines()[0].split()
    assert "Dep" in header
    row = next(line for line in out.splitlines() if "Paint walls" in line)
    assert " 2,3 " in row
    assert "Dep" not in run(capsys, "next")[1].splitlines()[0]
    assert "Paint walls" not in run(capsys, "next")[1]


@pytest.mark.usefixtures("five")
def test_blocked_and_blocking_virtual_tags_and_urgency(capsys: Capture) -> None:
    run(capsys, "5", "modify", "depends:3")
    assert [line.split()[0] for line in run(capsys, "+BLOCKING", "list")[1].splitlines()[2:3]] == [
        "3"
    ]
    tasks = export(capsys)
    assert tasks["three"]["urgency"] == pytest.approx(8.0, abs=0.1)
    assert tasks["five"]["urgency"] == pytest.approx(-5.0, abs=0.1)
    run(capsys, "config", "set", "urgency.blocking", "0")
    assert export(capsys)["three"]["urgency"] == pytest.approx(0.0, abs=0.1)


@pytest.mark.usefixtures("five")
def test_done_tells_which_tasks_are_unblocked(capsys: Capture) -> None:
    run(capsys, "5", "modify", "depends:3,4")
    assert run(capsys, "3", "done")[1] == "Completed task 3 'three'.\n"  # 4 still pending
    assert run(capsys, "3", "done")[1] == (  # four, renumbered 3
        "Completed task 3 'four'.\nTask 3 'five' is now unblocked.\n"
    )


@pytest.mark.usefixtures("five")
def test_info_names_dependencies_and_blocked_tasks(capsys: Capture) -> None:
    run(capsys, "5", "modify", "depends:3,2")
    out = run(capsys, "5", "info")[1]
    assert "Depends on  2 'two'\n" in out
    assert "            3 'three'\n" in out
    assert "Blocking  5 'five'\n" in run(capsys, "2", "info")[1]


@pytest.mark.usefixtures("five")
def test_blocking_is_reserved(capsys: Capture) -> None:
    assert run(capsys, "1", "modify", "+BLOCKING")[0] == 1
