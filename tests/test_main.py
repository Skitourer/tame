import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tame import __version__
from tame.__main__ import main
from tame.cli.commands import HANDLERS, HELP_COMMANDS, HELP_TOPICS, help_text
from tame.storage.migrations import SCHEMA_VERSION

Capture = pytest.CaptureFixture[str]


def run(capsys: Capture, *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_version_prints_app_and_schema(capsys: Capture) -> None:
    assert run(capsys, "version") == (
        0,
        f"tame {__version__} (schema {SCHEMA_VERSION})\n"
        "MIT License. See tk help license and tk help credits.\n",
        "",
    )


def test_version_rejects_args(capsys: Capture) -> None:
    code, _, err = run(capsys, "version", "extra")
    assert code == 1
    assert "extra" in err


def test_unknown_word_is_a_list_filter(capsys: Capture) -> None:
    run(capsys, "add", "Call", "bank")
    assert run(capsys, "frobnicate") == (2, "", "No matches.\n")
    assert "Call bank" in run(capsys, "bank")[1]


def test_ambiguous_command(capsys: Capture) -> None:
    assert run(capsys, "3", "d") == (1, "", "Ambiguous command 'd': delete, denotate, done\n")


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


def test_first_run_welcomes(capsys: Capture) -> None:
    for argv in ((), ("list",)):
        code, out, err = run(capsys, *argv)
        assert (code, err) == (0, "")
        assert out.splitlines()[0] == "Welcome to TAME! No tasks yet. Try:"
        assert "tk help tour" in out
        assert "tk config set language fr" in out


def test_no_welcome_with_a_filter_or_any_task(capsys: Capture) -> None:
    assert run(capsys, "+phone") == (2, "", "No matches.\n")
    assert run(capsys, "status:all", "list") == (2, "", "No matches.\n")
    run(capsys, "add", "x")
    run(capsys, "1", "done")
    assert run(capsys, "list") == (2, "", "No matches.\n")


def test_welcome_in_french(capsys: Capture) -> None:
    run(capsys, "config", "set", "language", "fr")
    out = run(capsys)[1]
    assert out.startswith("Bienvenue dans TAME !")
    assert "tk config set language en" in out


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
    # The full uuid: an 8-char prefix may be all digits, which reads as an id.
    assert run(capsys, uuid, "status:completed", "delete", "--yes")[1] == (
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
        "Virtual",
        "Priority",
        "Entered",
        "Modified",
        "Urgency",
    ]
    assert "PROJECT TAGGED UNBLOCKED" in out


# --- virtual tags (0.3) -------------------------------------------------------------


def test_virtual_tags_filter(capsys: Capture) -> None:
    run(capsys, "add", "late", "due:yesterday", "+x")
    run(capsys, "add", "soon", "due:+3d", "project:home")
    run(capsys, "add", "plain")
    assert descriptions(capsys, "+OVERDUE") == ["1 late"]
    assert descriptions(capsys, "+DUE") == ["2 soon"]
    assert descriptions(capsys, "-TAGGED", "-PROJECT") == ["3 plain"]
    assert descriptions(capsys, "+UNBLOCKED", "-OVERDUE", "+PROJECT") == ["2 soon"]
    assert run(capsys, "+OVERDUE", "done")[0] == 0
    assert run(capsys, "status:completed", "+OVERDUE", "list")[0] == 2  # pending only


@pytest.mark.parametrize("argv", [("add", "x", "+TODAY"), ("1", "modify", "+OVERDUE")])
def test_virtual_tags_cannot_be_set(capsys: Capture, argv: tuple[str, ...]) -> None:
    run(capsys, "add", "x")
    code, out, err = run(capsys, *argv)
    assert (code, out) == (1, "")
    assert err.startswith("'")
    assert "is a virtual tag" in err


def test_imported_tag_with_virtual_name_is_kept_and_removable(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdin_bytes(monkeypatch, b'[{"description": "imported", "tags": ["TODAY", "x"]}]')
    run(capsys, "import")
    assert json.loads(run(capsys, "export")[1])[0]["tags"] == ["TODAY", "x"]
    assert run(capsys, "+TODAY", "list")[0] == 2  # the virtual tag: no due date
    run(capsys, "1", "modify", "-TODAY")
    assert json.loads(run(capsys, "export")[1])[0]["tags"] == ["x"]


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
    assert run(capsys, "status:all", "list") == (2, "", "No matches.\n")


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


# --- config (roadmap step 7a) ----------------------------------------------------


def test_first_run_creates_config(capsys: Capture, tame_home: Path) -> None:
    run(capsys, "version")
    assert (tame_home / "config.toml").is_file()


def test_config_lists_settings_and_marks_changes(capsys: Capture) -> None:
    code, out, _ = run(capsys, "config")
    assert code == 0
    assert out.splitlines()[:3] == [
        'language = "en"',
        "confirm_threshold = 3",
        'date_format = "%Y-%m-%d"',
    ]
    assert 'undo.retention = "3m"' in out
    assert "urgency.pri_H = 6.0" in out
    assert "# default" not in out
    run(capsys, "config", "set", "confirm_threshold", "5")
    assert "confirm_threshold = 5  # default: 3" in run(capsys, "config")[1]


def test_config_get_set_unset(capsys: Capture) -> None:
    assert run(capsys, "config", "get", "undo.retention") == (0, "3m\n", "")
    assert run(capsys, "config", "set", "undo.retention", "1y") == (
        0,
        'undo.retention = "1y"\n',
        "",
    )
    assert run(capsys, "config", "get", "undo.retention")[1] == "1y\n"
    assert run(capsys, "config", "unset", "undo.retention") == (
        0,
        'undo.retention = "3m" (default)\n',
        "",
    )
    assert run(capsys, "config", "get", "color")[1] == "true\n"


def test_config_set_invalid_value(capsys: Capture, tame_home: Path) -> None:
    code, _, err = run(capsys, "config", "set", "color", "maybe")
    assert code == 1
    assert err == (
        f"Invalid value \"maybe\" for 'color' in {tame_home / 'config.toml'}: "
        "expected true or false.\n"
    )


def test_config_unknown_setting(capsys: Capture) -> None:
    assert run(capsys, "config", "get", "colour") == (
        1,
        "",
        "Unknown setting 'colour'. Run 'tk config' to list them.\n",
    )


@pytest.mark.parametrize("args", [["get"], ["set", "color"], ["frob"], ["path", "x"]])
def test_config_usage(capsys: Capture, args: list[str]) -> None:
    assert run(capsys, "config", *args) == (
        1,
        "",
        "Usage: tk config [get KEY | set KEY VALUE | unset KEY | path | edit]\n",
    )


def test_config_path(capsys: Capture, tame_home: Path) -> None:
    assert run(capsys, "config", "path") == (0, f"{tame_home / 'config.toml'}\n", "")


def test_config_rejects_filter(capsys: Capture) -> None:
    assert run(capsys, "+x", "config")[0] == 1


def test_invalid_config_blocks_commands_but_config_can_fix_it(
    capsys: Capture, tame_home: Path
) -> None:
    tame_home.mkdir()
    (tame_home / "config.toml").write_text("color = 1\n", encoding="utf-8")
    code, _, err = run(capsys, "list")
    assert code == 1
    assert "Invalid value 1 for 'color'" in err
    assert run(capsys, "config", "set", "color", "false")[0] == 0
    assert run(capsys, "list")[0] == 0


def test_config_edit_opens_editor_then_validates(
    capsys: Capture, tame_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_editor(argv: list[str], check: bool) -> None:
        calls.append(argv)
        Path(argv[-1]).write_text("confirm_threshold = -2\n", encoding="utf-8")

    monkeypatch.setenv("EDITOR", "myedit --wait")
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setattr("subprocess.run", fake_editor)
    code, _, err = run(capsys, "config", "edit")
    assert calls == [["myedit", "--wait", str(tame_home / "config.toml")]]
    assert code == 1
    assert "confirm_threshold" in err


def test_config_edit_editor_missing(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VISUAL", "no-such-editor-xyz")
    code, _, err = run(capsys, "config", "edit")
    assert code == 1
    assert err.startswith("Cannot start the editor 'no-such-editor-xyz'")


@pytest.mark.usefixtures("five_tasks")
def test_confirm_threshold_from_config(capsys: Capture) -> None:
    run(capsys, "config", "set", "confirm_threshold", "10")
    code, out, _ = run(capsys, "+t", "done")
    assert (code, out.count("Completed"), "?" in out) == (0, 5, False)


def test_date_format_from_config(capsys: Capture) -> None:
    run(capsys, "add", "x", "due:2026-12-15")
    run(capsys, "config", "set", "date_format", "%d/%m/%Y")
    assert "15/12/2026" in run(capsys, "list")[1]
    assert "15/12/2026 00:00:00" in run(capsys, "1", "info")[1]


def test_urgency_coefficients_from_config(capsys: Capture) -> None:
    run(capsys, "add", "tagged", "+x")
    run(capsys, "add", "high", "pri:H")
    run(capsys, "config", "set", "urgency.tags", "10")
    assert descriptions(capsys) == ["1 tagged", "2 high"]


def test_cold_start_does_not_import_tomlkit() -> None:
    code = (
        "import sys; from tame.__main__ import main; main(['list']); "
        "print('tomlkit' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.stdout.splitlines()[-1] == "False"


# --- help (roadmap step 7b) --------------------------------------------------------


def test_help_lists_implemented_commands_and_topics(capsys: Capture) -> None:
    code, out, err = run(capsys, "help")
    assert (code, err) == (0, "")
    lines = out.splitlines()
    assert lines[0] == "Usage: tk [filter] <command> [arguments]   (no command = list)"
    listed = [line.split()[0] for line in lines[3 : 3 + len(HELP_COMMANDS)]]
    assert listed == list(HELP_COMMANDS)
    assert "  add       Create a task" in lines
    assert "  export    Export tasks as Taskwarrior JSON" in lines
    assert "Topics: tk help filters | dates | urgency | tour | license | credits" in out


def test_help_covers_every_implemented_command() -> None:
    assert set(HELP_COMMANDS) == set(HANDLERS) | {"config", "help"}


@pytest.mark.parametrize("argv", [["help", "modify"], ["help", "mod"], ["modify", "--help"]])
def test_help_on_a_command(capsys: Capture, argv: list[str]) -> None:
    code, out, _ = run(capsys, *argv)
    assert code == 0
    assert out.startswith("Usage: tk <filter> modify [attr:value]")
    assert "\n\nChange tasks.\n\n" in out
    assert "tk 12 modify due:mon -phone" in out


@pytest.mark.parametrize(
    ("argv", "start"),
    [
        (["--help"], "Usage: tk [filter] <command>"),
        (["3", "done", "--help"], "Usage: tk <filter> done [--yes]"),
        (["add", "x", "--help"], "Usage: tk add <description>"),
        (["help", "--help"], "Usage: tk help [command | topic]"),
    ],
)
def test_help_flag(capsys: Capture, argv: list[str], start: str) -> None:
    code, out, _ = run(capsys, *argv)
    assert code == 0
    assert out.startswith(start)


def test_help_flag_after_double_dash_is_a_word(capsys: Capture) -> None:
    assert run(capsys, "add", "--", "use", "--help")[1] == "Created task 1.\n"


@pytest.mark.parametrize(
    ("topic", "text"),
    [
        ("filters", "project:home         project home and its sub-projects"),
        ("dates", "eow   eom   eoy"),
        ("urgency", "priority     H 6.0, M 3.9, L 1.8"),
        ("tour", "A two-minute tour. Type the commands in order."),
        ("license", "Permission is hereby granted, free of charge"),
        ("credits", "TAME Arranges My Errands, by Skitourer."),
    ],
)
def test_help_topics(capsys: Capture, topic: str, text: str) -> None:
    code, out, _ = run(capsys, "help", topic)
    assert code == 0
    assert text in out


@pytest.mark.parametrize("subject", list(HELP_COMMANDS) + list(HELP_TOPICS))
def test_every_help_text_exists(subject: str) -> None:
    text = help_text(subject)
    assert "help.cmd." not in text  # a missing key would show up as itself
    assert "help.topic." not in text


def test_help_unknown_subject(capsys: Capture) -> None:
    assert run(capsys, "help", "frob") == (
        1,
        "",
        "No help for 'frob'. Run 'tk help' for the list.\n",
    )
    assert run(capsys, "help", "d")[2] == "Ambiguous command 'd': delete, denotate, done\n"
    assert run(capsys, "help", "a", "b")[0] == 1


def test_help_works_with_an_invalid_config(capsys: Capture, tame_home: Path) -> None:
    tame_home.mkdir()
    (tame_home / "config.toml").write_text("color = 1\n", encoding="utf-8")
    assert run(capsys, "help", "config")[0] == 0


# --- French UI (roadmap step 7c) ---------------------------------------------------


def test_language_fr_translates_output(capsys: Capture) -> None:
    assert run(capsys, "config", "set", "language", "fr") == (0, 'language = "fr"\n', "")
    assert run(capsys, "add", "Appeler", "due:tomorrow") == (0, "Tâche 1 créée.\n", "")
    assert "Échéance" in run(capsys, "list")[1]
    assert run(capsys, "nothing") == (2, "", "Aucune tâche trouvée.\n")
    assert run(capsys, "help")[1].startswith("Usage : tk [filtre]")


def test_language_fr_keeps_commands_and_keywords(capsys: Capture) -> None:
    run(capsys, "config", "set", "language", "fr")
    run(capsys, "add", "x")
    assert run(capsys, "1", "modify", "due:fri")[0] == 0
    assert run(capsys, "1", "done")[1] == "Tâche 1 « x » terminée.\n"


def test_language_fr_confirm_accepts_oui(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    run(capsys, "config", "set", "language", "fr")
    run(capsys, "add", "x")
    answer(monkeypatch, "oui\n")
    code, out, _ = run(capsys, "1", "delete")
    assert code == 0
    assert out.startswith("Supprimer la tâche 1 « x » ? (o/N) ")
    run(capsys, "undo")
    answer(monkeypatch, "y\n")
    assert run(capsys, "1", "delete")[0] == 0


def test_config_errors_use_the_configured_language(capsys: Capture, tame_home: Path) -> None:
    tame_home.mkdir()
    config = tame_home / "config.toml"
    config.write_text('language = "fr"\ncolor = 1\n', encoding="utf-8")
    assert run(capsys, "list")[2].startswith("Valeur 1 invalide pour « color »")
    config.write_text('language = "xx"\n', encoding="utf-8")
    assert run(capsys, "list")[2].startswith("Invalid value \"xx\" for 'language'")
    config.write_text('language = "fr"\n[x\n', encoding="utf-8")
    assert run(capsys, "list")[2].startswith("Invalid settings file")


# --- export / import (roadmap step 8a) -------------------------------------------


def stdin_bytes(monkeypatch: pytest.MonkeyPatch, data: bytes) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(data)))


def test_status_all_lists_every_status(capsys: Capture) -> None:
    run(capsys, "add", "open")
    run(capsys, "add", "closed")
    run(capsys, "2", "done")
    out = run(capsys, "status:all", "list")[1]
    assert "open" in out
    assert "closed" in out


def test_export_empty_is_an_empty_array(capsys: Capture) -> None:
    assert run(capsys, "export") == (0, "[]\n", "")


def test_export_pending_by_default_all_with_status_all(capsys: Capture) -> None:
    run(capsys, "add", "Call", "bank", "+phone", "pri:H", "due:2026-12-15")
    run(capsys, "add", "closed")
    run(capsys, "2", "done")
    code, out, _ = run(capsys, "export")
    assert code == 0
    (task,) = json.loads(out)
    assert (task["id"], task["description"], task["tags"], task["priority"]) == (
        1,
        "Call bank",
        ["phone"],
        "H",
    )
    assert task["status"] == "pending"
    assert len(task["due"]) == 16 and task["due"].endswith("Z")
    assert "urgency" in task
    statuses = [t["status"] for t in json.loads(run(capsys, "status:all", "export")[1])]
    assert statuses == ["pending", "completed"]


def test_export_then_import_round_trip(capsys: Capture, tmp_path: Path, tame_home: Path) -> None:
    run(capsys, "add", "a", "project:home")
    run(capsys, "add", "b")
    run(capsys, "2", "done")
    exported = run(capsys, "status:all", "export")[1]
    backup = tmp_path / "backup.json"
    backup.write_text(exported, encoding="utf-8")
    assert run(capsys, "import", str(backup)) == (
        0,
        "Imported: 0 added, 0 updated, 2 skipped (not newer).\n",
        "",
    )
    (tame_home / "tasks.db").unlink()
    assert run(capsys, "import", str(backup))[1].startswith("Imported: 2 added")
    assert run(capsys, "status:all", "export")[1] == exported


def test_import_taskwarrior_file(capsys: Capture, tmp_path: Path) -> None:
    lines = [
        '{"description":"Water plants","entry":"20261101T080000Z","status":"waiting",'
        '"wait":"20261201T000000Z","uuid":"a1b2c3d4-0000-4000-8000-000000000001"}',
        '{"description":"Old","entry":"20261001T080000Z","end":"20261002T080000Z",'
        '"status":"completed","tags":["x"]}',
    ]
    path = tmp_path / "tw.json"
    path.write_text("\n".join(lines), encoding="utf-8")
    assert run(capsys, "import", str(path))[1] == (
        "Imported: 2 added, 0 updated, 0 skipped (not newer).\n"
    )
    assert "Water plants" in run(capsys, "list")[1]
    (task,) = json.loads(run(capsys, "export")[1])
    assert (task["status"], task["wait"]) == ("waiting", "20261201T000000Z")


def test_import_annotations_and_depends_survive_modify_and_undo(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = "a1b2c3d4-0000-4000-8000-000000000002"
    stdin_bytes(
        monkeypatch,
        json.dumps(
            [
                {
                    "description": "Call bank",
                    "uuid": "a1b2c3d4-0000-4000-8000-000000000001",
                    "annotations": [{"entry": "20261102T080000Z", "description": "ask Ann"}],
                    "depends": other,
                },
                {"description": "Find IBAN", "uuid": other},
            ]
        ).encode(),
    )
    assert run(capsys, "import")[0] == 0
    info = run(capsys, "1", "info")[1]
    assert "ask Ann" in info and other in info
    run(capsys, "1", "modify", "+phone")
    run(capsys, "undo")
    (task, _) = json.loads(run(capsys, "export")[1])
    assert task["annotations"] == [{"entry": "20261102T080000Z", "description": "ask Ann"}]
    assert task["depends"] == [other]
    assert "tags" not in task


def test_import_from_stdin_and_utf16(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    stdin_bytes(monkeypatch, b'[{"description": "from stdin"}]')
    assert run(capsys, "import")[1].startswith("Imported: 1 added")
    # PowerShell 5 `tk export > f.json` writes UTF-16 with a BOM.
    stdin_bytes(monkeypatch, '[{"description": "été"}]'.encode("utf-16"))
    assert run(capsys, "import", "-")[1].startswith("Imported: 1 added")
    assert "été" in run(capsys, "list")[1]


def test_import_errors(capsys: Capture, tmp_path: Path) -> None:
    assert run(capsys, "import", str(tmp_path / "missing.json"))[2].startswith("Cannot read ")
    bad = tmp_path / "bad.json"
    bad.write_text('[{"description": "ok"}, {"description": "x", "due": "soon"}]', "utf-8")
    assert run(capsys, "import", str(bad)) == (
        1,
        "",
        "Task 2 of the input: Invalid date: 'soon' (e.g. 2026-12-15, tomorrow, fri, eom, +3d)\n",
    )
    assert run(capsys, "status:all", "export")[1] == "[]\n"  # nothing imported
    bad.write_text("[{", encoding="utf-8")
    assert run(capsys, "import", str(bad))[2].startswith("Invalid JSON: ")
    assert run(capsys, "import", "a", "b")[0] == 1
    assert run(capsys, "1", "import")[0] == 1


def test_undo_import(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    stdin_bytes(monkeypatch, b'{"description": "a"}\n{"description": "b"}')
    run(capsys, "import")
    assert run(capsys, "undo")[1].startswith("Undid 'import'.")
    assert run(capsys, "status:all", "export")[1] == "[]\n"


# --- alias (roadmap step 8b) -----------------------------------------------------


def test_alias_install_and_remove(
    capsys: Capture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    monkeypatch.setenv("UV_TOOL_BIN_DIR", str(bin_dir))
    monkeypatch.setenv("PATH", str(bin_dir))
    path = bin_dir / ("task.cmd" if sys.platform == "win32" else "task")
    assert run(capsys, "alias", "install", "task") == (0, f"Created alias 'task': {path}\n", "")
    assert run(capsys, "alias", "remove", "task") == (0, f"Removed alias 'task': {path}\n", "")
    assert run(capsys, "alias", "remove", "task")[2] == f"No alias 'task' ({path} not found).\n"


def test_alias_warns_when_not_on_path(
    capsys: Capture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UV_TOOL_BIN_DIR", str(tmp_path / "bin"))
    monkeypatch.setenv("PATH", str(tmp_path))
    code, _, err = run(capsys, "alias", "install", "t")
    assert code == 0
    assert err.startswith("Warning: ") and "not in PATH" in err


@pytest.mark.parametrize(
    "args", [(), ("install",), ("add", "task"), ("install", "a", "b"), ("install", "tk")]
)
def test_alias_usage_errors(capsys: Capture, args: tuple[str, ...]) -> None:
    assert run(capsys, "alias", *args)[0] == 1


def test_alias_takes_no_filter(capsys: Capture) -> None:
    assert run(capsys, "3", "alias", "install", "task")[0] == 1


def test_tour_commands_all_work(
    capsys: Capture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UV_TOOL_BIN_DIR", str(tmp_path / "bin"))
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    lines = [line.strip() for line in help_text("tour").splitlines()]
    commands = [line.split("  ")[0].split(" > ")[0] for line in lines if line.startswith("tk ")]
    assert len(commands) == 15
    for command in commands:
        code, _, err = run(capsys, *command.split()[1:])
        assert (command, code, err) == (command, 0, "")


def test_help_license_lists_libraries(capsys: Capture) -> None:
    out = run(capsys, "help", "license")[1]
    assert out.startswith("TAME is released under the MIT License:\n\nMIT License")
    assert "Libraries installed with TAME, and their licenses:" in out
    assert any(
        line.split()[:1] == ["rich"] and line.split()[-1] == "MIT" for line in out.splitlines()
    )


def test_help_credits_in_french(capsys: Capture) -> None:
    run(capsys, "config", "set", "language", "fr")
    out = run(capsys, "help", "credits")[1]
    assert out.startswith("TAME Arranges My Errands, par Skitourer.")
    assert "Taskwarrior" in out


# --- print (v0.2.0) ---------------------------------------------------------------


def test_print_opens_the_page_in_the_browser(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    run(capsys, "add", "Buy", "milk", "project:errands")
    code, out, err = run(capsys, "print")
    assert (code, err) == (0, "")
    assert out.startswith("Opened in your browser for printing (or saving as PDF): ")
    (page,) = tmp_path.glob("tame-print-*.html")
    assert opened == [page.resolve().as_uri()]
    html = page.read_text(encoding="utf-8")
    assert "Buy milk" in html
    assert "window.print()" in html


def test_print_without_a_browser(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("webbrowser.open", lambda url: False)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    run(capsys, "add", "x")
    assert run(capsys, "print")[1].startswith("Open this file in a browser to print it: ")


def test_print_to_file(capsys: Capture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("webbrowser.open", lambda url: pytest.fail("must not open"))
    run(capsys, "add", "Call", "bank", "+phone")
    run(capsys, "add", "Buy", "milk", "+shopping")
    target = tmp_path / "list.html"
    assert run(capsys, "+shopping", "print", "--file", str(target)) == (0, f"Saved: {target}\n", "")
    html = target.read_text(encoding="utf-8")
    assert "Buy milk" in html
    assert "Call bank" not in html
    assert "<h1>Tasks: +shopping</h1>" in html
    assert "window.print()" not in html


def test_print_errors(capsys: Capture, tmp_path: Path) -> None:
    assert run(capsys, "print") == (2, "", "No matches.\n")
    run(capsys, "add", "x")
    assert run(capsys, "print", "--file")[0] == 1
    code, _, err = run(capsys, "print", "--file", str(tmp_path / "missing" / "x.html"))
    assert code == 1
    assert err.startswith("Cannot write ")


# --- next (0.3) ---------------------------------------------------------------------


def header(out: str) -> list[str]:
    return out.splitlines()[0].split()


def test_next_limits_and_tells_how_many_more(capsys: Capture) -> None:
    run(capsys, "config", "set", "next_limit", "2")
    run(capsys, "add", "low")
    run(capsys, "add", "high", "pri:H", "+x")
    run(capsys, "add", "mid", "pri:M", "project:home")
    code, out, err = run(capsys, "next")
    assert (code, err) == (0, "")
    assert header(out) == ["ID", "Project", "Pri", "Description", "Urg"]  # no Age, no Tags
    assert "high" in out and "mid" in out and "low" not in out
    assert out.splitlines()[-1] == "2 of 3 tasks. tk list shows them all."
    assert "of" not in run(capsys, "+home", "next")[1]


def test_next_leaves_out_blocked_tasks(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    first = "a1b2c3d4-0000-4000-8000-000000000001"
    data = [
        {"description": "first", "uuid": first},
        {"description": "blocked", "depends": [first]},
    ]
    stdin_bytes(monkeypatch, json.dumps(data).encode())
    run(capsys, "import")
    out = run(capsys, "next")[1]
    assert "first" in out and "blocked" not in out
    assert "blocked" in run(capsys, "list")[1]
    run(capsys, "1", "done")
    assert "blocked" in run(capsys, "n")[1]  # unique prefix; unblocked once first is done


def test_next_no_match_and_welcome(capsys: Capture) -> None:
    assert run(capsys, "next")[1].startswith("Welcome")
    run(capsys, "add", "x")
    assert run(capsys, "+nope", "next")[0] == 2


def test_default_command_next(capsys: Capture) -> None:
    run(capsys, "add", "x", "+tag")
    assert "Age" in header(run(capsys)[1])
    run(capsys, "config", "set", "default_command", "next")
    assert "Age" not in header(run(capsys)[1])
    assert "Age" not in header(run(capsys, "+tag")[1])
    assert "Age" in header(run(capsys, "list")[1])


@pytest.mark.parametrize(("key", "value"), [("default_command", "info"), ("next_limit", "0")])
def test_next_settings_validated(capsys: Capture, key: str, value: str) -> None:
    assert run(capsys, "config", "set", key, value)[0] == 1


# --- annotate / denotate (0.3) ------------------------------------------------------


def test_annotate_and_denotate_spec_examples(capsys: Capture) -> None:
    run(capsys, "add", "Call", "bank")
    assert run(capsys, "1", "annotate", "Call", "back", "Monday") == (
        0,
        "Annotated task 1 'Call bank'.\n",
        "",
    )
    run(capsys, "annotate", "1", "--", "done", "by", "mail")  # classic order, `--`
    assert "Call bank [2]" in run(capsys, "list")[1]
    assert "Call bank [2]" in run(capsys, "next")[1]
    info = run(capsys, "1", "info")[1]
    assert "Call back Monday" in info and "done by mail" in info
    assert run(capsys, "+ANNOTATED", "list")[0] == 0
    assert run(capsys, "1", "denotate", "Call") == (0, "Denotated task 1 'Call bank'.\n", "")
    assert "Call back Monday" not in run(capsys, "1", "info")[1]
    run(capsys, "undo")
    assert "Call back Monday" in run(capsys, "1", "info")[1]


def test_denotate_errors(capsys: Capture) -> None:
    run(capsys, "add", "x")
    assert run(capsys, "1", "denotate") == (2, "", "No note to remove.\n")
    run(capsys, "1", "annotate", "Call back")
    run(capsys, "1", "annotate", "Call bank")
    code, _, err = run(capsys, "1", "denotate", "call")
    assert code == 1
    assert err == (
        "Several notes of task 1 contain 'call': 'Call back', 'Call bank'. Give more of the text.\n"
    )
    assert run(capsys, "1", "denotate", "zzz")[0] == 2


def test_annotate_needs_filter_and_text(capsys: Capture) -> None:
    run(capsys, "add", "x")
    assert run(capsys, "annotate", "text")[0] == 1  # no filter
    assert run(capsys, "1", "annotate")[2].startswith("Nothing to annotate")


@pytest.mark.usefixtures("five_tasks")
def test_annotate_bulk_asks(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    answer(monkeypatch, "n\n")
    assert run(capsys, "+t", "annotate", "note")[1].startswith("Annotate 5 tasks? (y/N)")
    assert "[1]" not in run(capsys, "list")[1]
    run(capsys, "+t", "annotate", "note", "--yes")
    assert run(capsys, "list")[1].count("[1]") == 5
