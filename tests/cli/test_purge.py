"""``tk purge`` and ``tk purge --all`` (SPEC §5)."""

import io
import json
import os
import sys
from pathlib import Path

import pytest

from tame.__main__ import main
from tame.cli.commands import keyboard_input

Capture = pytest.CaptureFixture[str]


class TerminalInput(io.StringIO):
    """Keyboard input that says it is a terminal."""

    def isatty(self) -> bool:
        return True


def run(capsys: Capture, *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def type_in(monkeypatch: pytest.MonkeyPatch, text: str, *, terminal: bool = True) -> None:
    monkeypatch.setattr("sys.stdin", (TerminalInput if terminal else io.StringIO)(text))


def backups(home: Path) -> list[Path]:
    return sorted(home.glob("tame-*.db.bak"))


@pytest.fixture
def tasks(capsys: Capture) -> None:
    """Pending ``keep``, completed ``done``, deleted ``old`` (project old) and ``gone``."""
    for line in (["keep"], ["done"], ["old", "project:old"], ["gone"]):
        run(capsys, "add", *line)
    run(capsys, "2", "done")
    run(capsys, "2-3", "delete", "--yes")


def descriptions(capsys: Capture) -> list[str]:
    out = run(capsys, "status:all", "export")[1]
    return sorted(task["description"] for task in json.loads(out))


@pytest.mark.usefixtures("tasks")
def test_purge_spec_example_erases_deleted_tasks(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch, tame_home: Path
) -> None:
    type_in(monkeypatch, "y\n")
    code, out, err = run(capsys, "purge")
    [backup] = backups(tame_home)
    assert (code, err) == (0, "")
    assert out == (
        "Erase 2 deleted tasks for good? (y/N) Purged 2 tasks for good.\n"
        f"Backup of the database before the purge: {backup}\n"
        "A purge cannot be undone: tk undo has nothing left to revert.\n"
    )
    assert descriptions(capsys) == ["done", "keep"]
    assert run(capsys, "undo")[0] == 2


@pytest.mark.usefixtures("tasks")
def test_purge_with_filter_and_yes(capsys: Capture) -> None:
    code, out, _ = run(capsys, "project:old", "purge", "--yes")
    assert code == 0
    assert out.startswith("Purged 1 task for good.\n")
    assert descriptions(capsys) == ["done", "gone", "keep"]


@pytest.mark.usefixtures("tasks")
def test_purge_one_task_names_it(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    type_in(monkeypatch, "n\n")
    out = run(capsys, "project:old", "purge")[1]
    assert out.startswith("Erase deleted task ")
    assert out.endswith(" 'old' for good? (y/N) Cancelled: no task changed.\n")


@pytest.mark.usefixtures("tasks")
def test_purge_cancelled_changes_nothing(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch, tame_home: Path
) -> None:
    type_in(monkeypatch, "n\n")
    assert run(capsys, "purge")[0] == 0
    assert backups(tame_home) == []
    assert descriptions(capsys) == ["done", "gone", "keep", "old"]


def test_purge_nothing_deleted_exit_2(capsys: Capture, tame_home: Path) -> None:
    run(capsys, "add", "keep")
    assert run(capsys, "purge", "--yes") == (2, "", "Nothing to purge.\n")
    assert backups(tame_home) == []


@pytest.mark.usefixtures("tasks")
def test_purge_rejects_other_status(capsys: Capture) -> None:
    code, _, err = run(capsys, "status:pending", "purge")
    assert code == 1
    assert "only erases deleted tasks" in err


@pytest.mark.usefixtures("tasks")
@pytest.mark.parametrize("token", ["pu", "pur", "purg"])
def test_purge_needs_its_full_name(capsys: Capture, token: str) -> None:
    run(capsys, token, "--yes")  # not purge: whatever it does, nothing is erased
    assert descriptions(capsys) == ["done", "gone", "keep", "old"]


@pytest.mark.usefixtures("tasks")
def test_purge_all_needs_y_then_the_word(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch, tame_home: Path
) -> None:
    type_in(monkeypatch, "y\npurge\n")
    code, out, _ = run(capsys, "purge", "--all")
    assert code == 0
    assert out.startswith(
        "Erase ALL 4 tasks (pending, completed, deleted) for good? (y/N) "
        "Type purge to confirm: Purged 4 tasks for good.\n"
    )
    assert len(backups(tame_home)) == 1
    assert descriptions(capsys) == []


@pytest.mark.usefixtures("tasks")
@pytest.mark.parametrize("typed", ["y\nPurge\n", "y\nyes\n", "y\n", "n\npurge\n"])
def test_purge_all_wrong_answer_cancels(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch, tame_home: Path, typed: str
) -> None:
    type_in(monkeypatch, typed)
    code, out, _ = run(capsys, "purge", "--all")
    assert code == 0
    assert out.endswith("Cancelled: no task changed.\n")
    assert backups(tame_home) == []
    assert descriptions(capsys) == ["done", "gone", "keep", "old"]


@pytest.mark.usefixtures("tasks")
def test_purge_all_yes_still_asks_for_the_word(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    type_in(monkeypatch, "purge\n")
    out = run(capsys, "purge", "--all", "--yes")[1]
    assert out.startswith("Type purge to confirm: Purged 4 tasks for good.\n")


@pytest.mark.usefixtures("tasks")
def test_purge_all_in_french_still_wants_purge(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    run(capsys, "config", "set", "language", "fr")
    type_in(monkeypatch, "o\npurge\n")
    out = run(capsys, "purge", "--all")[1]
    assert "Tapez purge pour confirmer : 4 tâches effacées définitivement." in out


@pytest.mark.usefixtures("tasks")
def test_purge_all_needs_a_terminal(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    type_in(monkeypatch, "y\npurge\n", terminal=False)
    code, _, err = run(capsys, "purge", "--all", "--yes")
    assert code == 1
    assert "must be confirmed in a terminal" in err
    assert descriptions(capsys) == ["done", "gone", "keep", "old"]


@pytest.mark.usefixtures("tasks")
def test_purge_all_takes_no_filter(capsys: Capture) -> None:
    code, _, err = run(capsys, "project:old", "purge", "--all")
    assert code == 1
    assert "takes no filter" in err


def test_purge_all_empty_database_exit_2(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    type_in(monkeypatch, "")
    assert run(capsys, "purge", "--all")[:2] == (2, "")


@pytest.mark.usefixtures("tasks")
def test_backup_failure_purges_nothing(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch, tame_home: Path
) -> None:
    def fail(self: object, target: Path) -> None:
        from tame.errors import StorageError

        raise StorageError("error.backup", path=str(target), detail="disk full")

    monkeypatch.setattr("tame.storage.repo.TaskRepo.backup", fail)
    code, _, err = run(capsys, "purge", "--yes")
    assert code != 0
    assert "disk full. Nothing was purged." in err
    assert descriptions(capsys) == ["done", "gone", "keep", "old"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows NUL device")
def test_nul_is_no_keyboard(monkeypatch: pytest.MonkeyPatch) -> None:
    with open(os.devnull, encoding="utf-8") as nul:  # noqa: PTH123 - text stream on NUL
        assert nul.isatty()  # what Windows claims
        monkeypatch.setattr("sys.stdin", nul)
        assert not keyboard_input()


def test_purge_all_from_nul_is_a_usage_error(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    run(capsys, "add", "keep")
    with open(os.devnull, encoding="utf-8") as nul:  # noqa: PTH123 - text stream on NUL
        monkeypatch.setattr("sys.stdin", nul)
        code, _, err = run(capsys, "purge", "--all", "--yes")
    assert code == 1
    assert "must be confirmed in a terminal" in err
