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


def test_unknown_command_is_usage_error(capsys: Capture) -> None:
    code, out, err = run(capsys, "frobnicate")
    assert (code, out) == (1, "")
    assert "frobnicate" in err


def test_add_prints_created_id(capsys: Capture, tame_home: Path) -> None:
    # SPEC §5 example without due: (dates arrive in step 5).
    assert run(capsys, "add", "Call", "bank", "project:home", "+phone", "pri:H") == (
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
    code, _, err = run(capsys, "add", "x", "due:tomorrow")
    assert code == 1
    assert err == "Unknown attribute: due\n"


def test_list_shows_tasks_and_hides_empty_columns(capsys: Capture) -> None:
    run(capsys, "add", "Call", "bank", "project:home", "+phone", "pri:H")
    run(capsys, "add", "Buy", "milk")
    code, out, err = run(capsys, "list")
    assert (code, err) == (0, "")
    lines = out.splitlines()
    header = lines[0].split()
    assert header == ["ID", "Age", "Project", "Tags", "Pri", "Description"]
    assert "Due" not in out
    rows = [line.split() for line in lines[2:] if line.strip()]
    assert rows[0][0] == "1"
    assert rows[0][2:] == ["home", "phone", "H", "Call", "bank"]
    assert rows[1][0] == "2"
    assert rows[1][2:] == ["Buy", "milk"]


def test_no_args_means_list(capsys: Capture) -> None:
    run(capsys, "add", "Buy", "milk")
    code, out, _ = run(capsys)
    assert code == 0
    assert "Buy milk" in out


def test_list_empty_is_no_match(capsys: Capture) -> None:
    assert run(capsys, "list") == (2, "", "No matches.\n")


def test_list_rejects_filters_for_now(capsys: Capture) -> None:
    assert run(capsys, "list", "+x")[0] == 1


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
