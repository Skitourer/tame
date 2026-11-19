import io
import subprocess
import sys
from pathlib import Path

import pytest

from tame import __version__
from tame.__main__ import main
from tame.storage.migrations import SCHEMA_VERSION

Capture = pytest.CaptureFixture[str]


def run(capsys: Capture, *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_version_prints_app_and_schema(capsys: Capture) -> None:
    assert run(capsys, "version") == (0, f"tame {__version__} (schema {SCHEMA_VERSION})\n", "")


def test_version_rejects_args(capsys: Capture) -> None:
    code, _, err = run(capsys, "version", "extra")
    assert code == 1
    assert "extra" in err


def test_unknown_word_is_a_list_filter(capsys: Capture) -> None:
    run(capsys, "add", "Call", "bank")
    assert run(capsys, "frobnicate") == (2, "", "No matches.\n")
    assert "Call bank" in run(capsys, "bank")[1]


def test_ambiguous_command(capsys: Capture) -> None:
    assert run(capsys, "3", "d") == (1, "", "Ambiguous command 'd': delete, done\n")


@pytest.mark.parametrize("command", ["export", "import", "alias"])
def test_later_commands_not_implemented(capsys: Capture, command: str) -> None:
    code, _, err = run(capsys, command)
    assert code == 1
    assert err == f"Command '{command}' is not implemented yet.\n"


def test_filter_not_allowed(capsys: Capture) -> None:
    assert run(capsys, "3", "version") == (1, "", "Command 'version' does not accept a filter.\n")


def test_add_prints_created_id(capsys: Capture, tame_home: Path) -> None:
    # SPEC §5 example.
    argv = ("add", "Call", "bank", "project:home", "+phone", "due:tomorrow", "pri:H")
    assert run(capsys, *argv) == (
        0,
        "Created task 1.\n",
        "",
    )
    assert run(capsys, "add", "Buy", "milk")[1] == "Created task 2.\n"
    assert (tame_home / "tasks.db").is_file()


def test_add_invalid_is_usage_error(capsys: Capture) -> None:
    code, out, err = run(capsys, "add", "x", "pri:Z")
    assert (code, out) == (1, "")
    assert err == "Invalid priority: 'Z' (expected H, M or L)\n"


def test_add_unknown_attribute(capsys: Capture) -> None:
    code, _, err = run(capsys, "add", "x", "wait:tomorrow")
    assert code == 1
    assert err == "Unknown attribute: wait\n"


def test_list_shows_tasks_and_hides_empty_columns(capsys: Capture) -> None:
    run(capsys, "add", "Call", "bank", "project:home", "+phone", "pri:H")
    run(capsys, "add", "Buy", "milk")
    code, out, err = run(capsys, "list")
    assert (code, err) == (0, "")
    lines = out.splitlines()
    header = lines[0].split()
    assert header == ["ID", "Age", "Project", "Tags", "Pri", "Description", "Urg"]
    assert "Due" not in out
    rows = [line.split() for line in lines[2:] if line.strip()]
    assert rows[0][0] == "1"
    assert rows[0][2:] == ["home", "phone", "H", "Call", "bank", "8.0"]
    assert rows[1][0] == "2"
    assert rows[1][2:] == ["Buy", "milk", "0.0"]


def test_no_args_means_list(capsys: Capture) -> None:
    run(capsys, "add", "Buy", "milk")
    code, out, _ = run(capsys)
    assert code == 0
    assert "Buy milk" in out


def test_list_empty_is_no_match(capsys: Capture) -> None:
    assert run(capsys, "list") == (2, "", "No matches.\n")


def listed_ids(out: str) -> list[str]:
    return [line.split()[0] for line in out.splitlines()[2:] if line.strip()]


@pytest.fixture
def three_tasks(capsys: Capture) -> None:
    run(capsys, "add", "Call", "bank", "project:home", "+phone", "pri:H")
    run(capsys, "add", "Fix", "fence", "project:home.garden", "+diy")
    run(capsys, "add", "Write", "report", "project:work", "+phone", "pri:L")


@pytest.mark.usefixtures("three_tasks")
@pytest.mark.parametrize(
    "argv",
    [
        ["project:home", "list"],  # SPEC §5 example (TW order)
        ["list", "project:home"],  # classic order
        ["project:home"],  # no command = list
    ],
)
def test_list_spec_example_both_orders(capsys: Capture, argv: list[str]) -> None:
    code, out, _ = run(capsys, *argv)
    assert code == 0
    assert listed_ids(out) == ["1", "2"]


@pytest.mark.usefixtures("three_tasks")
@pytest.mark.parametrize(
    ("argv", "ids"),
    [
        (["+phone", "list"], ["1", "3"]),
        (["-phone"], ["2"]),
        (["pri:H"], ["1"]),
        (["pri:"], ["2"]),
        (["2-3", "list"], ["3", "2"]),  # sorted by urgency
        (["1,3", "+phone", "report"], ["3"]),
        (["list", "FENCE"], ["2"]),
        (["project:home.garden", "list"], ["2"]),
    ],
)
def test_list_filters(capsys: Capture, argv: list[str], ids: list[str]) -> None:
    code, out, _ = run(capsys, *argv)
    assert (code, listed_ids(out)) == (0, ids)


@pytest.mark.usefixtures("three_tasks")
def test_list_no_match_exit_2(capsys: Capture) -> None:
    assert run(capsys, "status:completed", "list") == (2, "", "No matches.\n")
    assert run(capsys, "+nope") == (2, "", "No matches.\n")


def test_list_unknown_attribute(capsys: Capture) -> None:
    assert run(capsys, "due.on:fri", "list") == (1, "", "Unknown attribute: due.on\n")


def test_internal_error_exit_code(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_: object) -> int:
        raise RuntimeError("kaboom")

    monkeypatch.setattr("tame.cli.commands.run", boom)
    code, _, err = run(capsys, "version")
    assert code == 3
    assert err.startswith("Internal error:")
    assert "kaboom" in err


def test_module_entry_point() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "tame", "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.startswith(f"tame {__version__}")


def test_redirected_output_is_utf8() -> None:
    def tk(*args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, "-m", "tame", *args], capture_output=True, check=True
        )

    tk("add", "Écrire", "le", "rapport")
    assert "Écrire le rapport".encode() in tk("list").stdout


def test_cold_start_does_not_import_rich() -> None:
    code = (
        "import sys; from tame.__main__ import main; main(['version']); "
        "print('rich' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.splitlines()[-1] == "False"


# --- done / delete / modify / info (roadmap step 4) ---------------------------


def answer(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    """Feed ``text`` to the confirmation prompt."""
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def descriptions(capsys: Capture, *argv: str) -> list[str]:
    """Return ``(id, description)`` cells of ``tk <argv>`` as "id description" strings."""
    code, out, _ = run(capsys, *argv, "list")
    if code:
        return []
    return [" ".join((line.split()[0], line.split()[-2])) for line in out.splitlines()[2:] if line]


@pytest.fixture
def five_tasks(capsys: Capture) -> None:
    for name in ("one", "two", "three", "four", "five"):
        run(capsys, "add", name, "+t")


@pytest.mark.usefixtures("five_tasks")
def test_done_spec_example_renumbers(capsys: Capture) -> None:
    assert run(capsys, "3,5", "done") == (
        0,
        "Completed task 3 'three'.\nCompleted task 5 'five'.\n",
        "",
    )
    assert descriptions(capsys) == ["1 one", "2 two", "3 four"]
    code, out, _ = run(capsys, "status:completed", "list")
    assert code == 0
    assert out.splitlines()[0].split()[:2] == ["Age", "Tags"]  # no id once completed
    assert "three" in out
    assert "five" in out


@pytest.mark.usefixtures("five_tasks")
def test_done_classic_order(capsys: Capture) -> None:
    assert run(capsys, "done", "2")[1] == "Completed task 2 'two'.\n"


@pytest.mark.usefixtures("five_tasks")
def test_done_over_threshold_asks(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    answer(monkeypatch, "n\n")
    code, out, _ = run(capsys, "+t", "done")
    assert code == 0
    assert out == "Complete 5 tasks? (y/N) Cancelled: no task changed.\n"
    assert len(descriptions(capsys)) == 5

    answer(monkeypatch, "Y\n")
    code, out, _ = run(capsys, "+t", "done")
    assert out.startswith("Complete 5 tasks? (y/N) Completed task 1 'one'.")
    assert run(capsys, "list") == (2, "", "No matches.\n")


@pytest.mark.usefixtures("five_tasks")
def test_done_at_threshold_does_not_ask(capsys: Capture) -> None:
    code, out, _ = run(capsys, "1-3", "done")
    assert (code, out.count("Completed")) == (0, 3)


@pytest.mark.usefixtures("five_tasks")
def test_end_of_input_means_no(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    answer(monkeypatch, "")
    code, out, _ = run(capsys, "+t", "done")
    assert code == 0
    assert out.endswith("Cancelled: no task changed.\n")
    assert len(descriptions(capsys)) == 5


@pytest.mark.usefixtures("five_tasks")
def test_yes_skips_prompt(capsys: Capture) -> None:
    code, out, _ = run(capsys, "+t", "done", "--yes")
    assert (code, out.count("Completed"), "?" in out) == (0, 5, False)


@pytest.mark.usefixtures("five_tasks")
def test_delete_spec_example_always_asks(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    answer(monkeypatch, "y\n")
    assert run(capsys, "4", "delete") == (
        0,
        "Delete task 4 'four'? (y/N) Deleted task 4 'four'.\n",
        "",
    )
    assert descriptions(capsys) == ["1 one", "2 two", "3 three", "4 five"]
    code, out, _ = run(capsys, "status:deleted", "list")
    assert code == 0
    assert "four" in out


@pytest.mark.usefixtures("five_tasks")
def test_delete_with_yes(capsys: Capture) -> None:
    assert run(capsys, "delete", "--yes", "1") == (0, "Deleted task 1 'one'.\n", "")


@pytest.mark.usefixtures("five_tasks")
def test_done_by_uuid_of_completed_task_names_it_by_uuid(capsys: Capture) -> None:
    run(capsys, "1", "done")
    out = run(capsys, "status:completed", "info")[1]
    uuid = next(line.split()[1] for line in out.splitlines() if line.startswith("UUID"))
    assert run(capsys, uuid[:8], "status:completed", "delete", "--yes")[1] == (
        f"Deleted task {uuid[:8]} 'one'.\n"
    )


@pytest.mark.parametrize("command", ["done", "delete", "modify"])
def test_write_commands_need_a_filter(capsys: Capture, command: str) -> None:
    code, _, err = run(capsys, command)
    assert code == 1
    assert err == f"Command '{command}' needs a filter, e.g. 'tk 3 {command}'.\n"


@pytest.mark.parametrize("command", ["done", "delete --yes", "modify +x", "info"])
def test_write_commands_no_match(capsys: Capture, command: str) -> None:
    name, *args = command.split()
    assert run(capsys, "9", name, *args) == (2, "", "No matches.\n")


def test_modify_spec_example(capsys: Capture) -> None:
    # SPEC §5: `tk 12 modify due:mon -phone`.
    run(capsys, "add", "Call", "bank", "+phone", "pri:H")
    assert run(capsys, "1", "modify", "due:mon", "-phone") == (
        0,
        "Modified task 1 'Call bank'.\n",
        "",
    )
    code, out, _ = run(capsys, "1", "info")
    assert code == 0
    assert "Due" in out
    assert "phone" not in out
    run(capsys, "1", "modify", "due:")
    assert "Due" not in run(capsys, "1", "info")[1]


def test_modify_replaces_description(capsys: Capture) -> None:
    run(capsys, "add", "Call", "bank")
    assert run(capsys, "modify", "1", "Call", "the", "bank", "+urgent") == (
        0,
        "Modified task 1 'Call bank'.\n",
        "",
    )
    assert descriptions(capsys, "+urgent") == ["1 bank"]
    assert "Call the bank" in run(capsys, "1", "info")[1]


def test_modify_unchanged(capsys: Capture) -> None:
    run(capsys, "add", "x", "+a")
    assert run(capsys, "1", "modify", "+a") == (0, "No task changed.\n", "")


def test_modify_without_mods_is_usage_error(capsys: Capture) -> None:
    run(capsys, "add", "x")
    code, _, err = run(capsys, "1", "modify")
    assert code == 1
    assert err.startswith("Nothing to modify")


@pytest.mark.usefixtures("five_tasks")
def test_modify_bulk_asks(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    answer(monkeypatch, "yes\n")
    out = run(capsys, "+t", "modify", "pri:H")[1]
    assert out.startswith("Modify 5 tasks? (y/N) Modified task 1 'one'.")
    assert descriptions(capsys, "pri:H") == ["1 one", "2 two", "3 three", "4 four", "5 five"]


def test_info_spec_example(capsys: Capture) -> None:
    run(capsys, "add", "Call", "bank", "project:home", "+phone", "pri:H")
    code, out, err = run(capsys, "1", "info")
    assert (code, err) == (0, "")
    labels = [line.split()[0] for line in out.splitlines()[2:] if line.strip()]
    assert labels == [
        "ID",
        "UUID",
        "Description",
        "Status",
        "Project",
        "Tags",
        "Priority",
        "Entered",
        "Modified",
        "Urgency",
    ]


def test_info_without_filter_shows_all_pending(capsys: Capture) -> None:
    run(capsys, "add", "one")
    run(capsys, "add", "two")
    out = run(capsys, "info")[1]
    assert out.count("UUID") == 2


# --- dates and urgency (roadmap step 5) ----------------------------------------


def test_list_sorted_by_urgency(capsys: Capture) -> None:
    run(capsys, "add", "plain")
    run(capsys, "add", "overdue", "due:-8d")
    run(capsys, "add", "high", "pri:H")
    run(capsys, "add", "tagged", "+x")
    assert descriptions(capsys) == ["2 overdue", "3 high", "4 tagged", "1 plain"]


def test_list_shows_due_date_and_urgency(capsys: Capture) -> None:
    run(capsys, "add", "Pay", "rent", "due:2026-12-15")
    code, out, _ = run(capsys, "list")
    assert code == 0
    assert out.splitlines()[0].split() == ["ID", "Age", "Due", "Description", "Urg"]
    assert "2026-12-15" in out


def test_due_filter_spec_example(capsys: Capture) -> None:
    run(capsys, "add", "soon", "due:today")
    run(capsys, "add", "later", "due:+30d")
    run(capsys, "add", "never")
    assert descriptions(capsys, "due.before:+7d") == ["1 soon"]
    assert descriptions(capsys, "due.after:today") == ["2 later"]


def test_add_invalid_due(capsys: Capture) -> None:
    assert run(capsys, "add", "x", "due:someday") == (
        1,
        "",
        "Invalid date: 'someday' (e.g. 2026-12-15, tomorrow, fri, eom, +3d)\n",
    )


# --- undo (roadmap step 6) -------------------------------------------------------


@pytest.mark.usefixtures("five_tasks")
def test_undo_spec_example(capsys: Capture) -> None:
    run(capsys, "2,4", "done")
    assert run(capsys, "undo") == (
        0,
        "Undid 'done'.\nRestored task 2 'two'.\nRestored task 4 'four'.\n",
        "",
    )
    assert descriptions(capsys) == ["1 one", "2 two", "3 three", "4 four", "5 five"]


def test_undo_add(capsys: Capture) -> None:
    run(capsys, "add", "Buy", "milk")
    assert run(capsys, "undo") == (0, "Undid 'add'.\nRemoved task 1 'Buy milk'.\n", "")
    assert run(capsys, "list") == (2, "", "No matches.\n")


def test_undo_modify(capsys: Capture) -> None:
    run(capsys, "add", "Call", "bank", "+phone")
    run(capsys, "1", "modify", "-phone", "Call", "the", "bank")
    assert run(capsys, "undo")[1] == "Undid 'modify'.\nRestored task 1 'Call bank'.\n"
    assert descriptions(capsys, "+phone") == ["1 bank"]


def test_undo_nothing_exit_2(capsys: Capture) -> None:
    assert run(capsys, "undo") == (2, "", "Nothing to undo.\n")


def test_undo_rejects_args(capsys: Capture) -> None:
    assert run(capsys, "undo", "3")[0] == 1
    assert run(capsys, "3", "undo")[0] == 1
