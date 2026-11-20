import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tame.__main__ import main
from tame.cli.commands import HELP_TOPICS
from tame.cli.completion import DATE_KEYWORDS, Data, candidates, complete, script
from tame.cli.parser import COMMANDS
from tame.core.models import VIRTUAL_TAGS
from tame.errors import UsageError
from tame.storage.repo import DB_FILENAME

Capture = pytest.CaptureFixture[str]


class FakeData(Data):
    def __init__(self) -> None:
        super().__init__(Path("missing.db"))

    def tags(self) -> list[str]:
        return ["home", "phone"]

    def projects(self) -> list[str]:
        return ["home", "home.garden", "work"]


def complete_line(line: str) -> list[str]:
    """Candidates for the last word of ``line`` (a trailing space = an empty word)."""
    words = line.split(" ")
    return candidates(words[:-1], words[-1], FakeData())


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("mo", ["modify"]),
        ("a", ["add", "alias", "annotate"]),
        ("+ph", ["+phone"]),
        ("-h", ["-home"]),
        ("+OV", ["+OVERDUE"]),
        ("project:ho", ["project:home", "project:home.garden"]),
        ("pri:", ["pri:H", "pri:M", "pri:L"]),
        ("status:", ["status:pending", "status:completed", "status:deleted", "status:all"]),
        ("due.before:e", ["due.before:eow", "due.before:eom", "due.before:eoy"]),
        ("pro", ["project:"]),
        ("3 modify p", ["project:", "pri:"]),
        ("3 modify +O", []),  # virtual tags cannot be set
        ("add x w", ["wait:"]),
        ("add x wait:to", ["wait:today", "wait:tomorrow"]),
        ("list st", ["status:"]),
        ("help f", ["filters"]),
        ("help list ", []),
        ("config ", ["get", "set", "unset", "path", "edit"]),
        ("config set la", ["language"]),
        ("config set language ", ["en", "fr"]),
        ("config set color ", ["true", "false"]),
        ("config set default_command ", ["list", "next"]),
        ("config set next_limit ", []),
        ("alias ", ["install", "remove"]),
        ("completion ", ["powershell", "bash"]),
        ("3 annotate Ca", []),
        ("import ", []),
        ("undo ", []),
        ("add -- +ph", []),
        ("c", ["completion", "config"]),
        ("x:", []),
    ],
)
def test_candidates(line: str, expected: list[str]) -> None:
    assert complete_line(line) == expected


def test_first_word_offers_commands_and_filter_attributes() -> None:
    assert complete_line("") == [
        *COMMANDS,
        "project:",
        "pri:",
        "status:",
        "due.before:",
        "due.after:",
    ]


def test_virtual_tags_and_date_keywords_are_complete() -> None:
    assert complete_line("+") == ["+home", "+phone", *(f"+{tag}" for tag in sorted(VIRTUAL_TAGS))]
    assert complete_line("due.after:") == [f"due.after:{word}" for word in DATE_KEYWORDS]


def test_help_topics_match_the_help_command() -> None:
    assert complete_line("help ")[-len(HELP_TOPICS) :] == list(HELP_TOPICS)


def test_data_reads_pending_tasks_only(capsys: Capture, tame_home: Path) -> None:
    main(["add", "a", "+phone", "project:home"])
    main(["add", "b", "+old", "project:archive"])
    main(["2", "done"])
    capsys.readouterr()
    data = Data(tame_home / DB_FILENAME)
    assert (data.tags(), data.projects()) == (["phone"], ["home"])


def test_data_never_creates_the_database(tmp_path: Path) -> None:
    data = Data(tmp_path / DB_FILENAME)
    assert (data.tags(), data.projects()) == ([], [])
    assert not (tmp_path / DB_FILENAME).exists()


def test_complete_protocol(tmp_path: Path) -> None:
    db = tmp_path / DB_FILENAME
    assert complete(["_mod"], db) == "modify\n"
    assert complete(["_", "help"], db).startswith("add\n")
    assert complete([], db) == ""
    assert complete(["mod"], db) == ""  # no `_` prefix: not from our scripts


def test_hidden_command_through_main(capsys: Capture) -> None:
    assert main(["_complete", "_ver"]) == 0
    assert capsys.readouterr().out == "version\n"
    assert main(["help"]) == 0
    assert "_complete" not in capsys.readouterr().out


def test_cold_complete_does_not_import_rich_or_tomlkit() -> None:
    code = (
        "import sys; from tame.__main__ import main; main(['_complete', '_l']); "
        "print('rich' in sys.modules, 'tomlkit' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.splitlines()[-1] == "False False"


# --- Scripts ---------------------------------------------------------------------------


def test_script_names_and_unknown_shell() -> None:
    assert "-CommandName tk, tame, task" in script("powershell", ["tk", "tame", "task"])
    assert script("bash", ["tk", "tame"]).rstrip().endswith("-F _tame_complete tk tame")
    with pytest.raises(UsageError) as exc:
        script("cmd", ["tk"])
    assert exc.value.key == "error.completion_shell"


def test_completion_command(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tame.alias.installed", lambda: ["task"])
    assert main(["completion", "powershell"]) == 0
    assert "-CommandName tk, tame, task" in capsys.readouterr().out
    assert main(["completion"]) == 1
    assert capsys.readouterr().err == (
        "Usage: tk completion powershell | bash (prints the script). "
        "To turn Tab completion on: tk config set completion true\n"
    )
    assert main(["completion", "powershell", "x"]) == 1
    assert capsys.readouterr().err.startswith("Usage: tk completion")
    assert main(["completion", "cmd"]) == 1
    assert capsys.readouterr().err == "Unknown shell 'cmd': use one of powershell, bash.\n"


@pytest.mark.skipif(shutil.which("powershell") is None, reason="needs Windows PowerShell")
def test_powershell_script_parses() -> None:
    check = (
        "$errors = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseInput("
        "[Console]::In.ReadToEnd(), [ref]$null, [ref]$errors); "
        "if ($errors) { $errors | ForEach-Object { $_.Message }; exit 1 }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", check],
        input=script("powershell", ["tk"]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None, reason="needs bash (Linux CI)"
)
def test_bash_script_parses() -> None:
    result = subprocess.run(
        ["bash", "-n"], input=script("bash", ["tk"]), capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_alias_installed_lists_tame_shims(tmp_path: Path) -> None:
    from tame import alias

    alias.install("task", tmp_path)
    other = tmp_path / ("other.cmd" if sys.platform == "win32" else "other")
    other.write_text("not ours", encoding="utf-8")
    assert alias.installed(tmp_path) == ["task"]
    assert alias.installed(tmp_path / "missing") == []
