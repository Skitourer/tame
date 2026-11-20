import codecs
from pathlib import Path

import pytest

from tame.__main__ import main
from tame.cli import shellprofile
from tame.cli.shellprofile import BEGIN, END, Profile, edit_block, reconcile
from tame.cli.shellprofile import discover as real_discover  # before the autouse guard
from tame.core.service import TaskService

Capture = pytest.CaptureFixture[str]
NAMES = ["tk", "tame"]


# --- edit_block --------------------------------------------------------------------------


def test_edit_block_adds_replaces_and_removes() -> None:
    added = edit_block("Set-Alias ll ls\n", "one", "\n")
    assert added == f"Set-Alias ll ls\n\n{BEGIN}\none\n{END}\n"
    replaced = edit_block(added + "# mine\n", "two\nlines", "\n")
    assert replaced == f"Set-Alias ll ls\n\n{BEGIN}\ntwo\nlines\n{END}\n# mine\n"
    assert edit_block(replaced, None, "\n") == "Set-Alias ll ls\n\n# mine\n"
    assert edit_block("", "x", "\r\n") == f"{BEGIN}\r\nx\r\n{END}\r\n"
    assert edit_block("", None, "\n") == ""


# --- reconcile -----------------------------------------------------------------------------


def profiles_in(tmp_path: Path, policy: str = "RemoteSigned") -> list[Profile]:
    return [Profile("powershell", str(tmp_path / "ps" / "profile.ps1"), policy)]


def test_tip_once_while_never_set_up(service: TaskService, tmp_path: Path) -> None:
    calls: list[int] = []

    def find() -> list[Profile]:
        calls.append(1)
        return profiles_in(tmp_path)

    assert reconcile(service, False, NAMES, find=find) == [
        "Tip: Tab completion is available: tk config set completion true"
    ]
    assert reconcile(service, False, NAMES, find=find) == []
    assert calls == []  # disabled and never set up: no shell is even asked


def test_enable_writes_block_and_disable_removes_it(service: TaskService, tmp_path: Path) -> None:
    path = tmp_path / "ps" / "profile.ps1"
    find = lambda: profiles_in(tmp_path)  # noqa: E731
    assert reconcile(service, True, NAMES, explicit=True, find=find) == [
        f"Tab completion enabled in {path}. Open a new terminal to use it."
    ]
    text = path.read_text(encoding="utf-8")
    assert BEGIN in text and "Register-ArgumentCompleter" in text and "tk, tame" in text
    assert reconcile(service, True, NAMES, find=find) == []  # up to date: silent
    assert reconcile(service, True, NAMES, explicit=True, find=find) == [
        f"Tab completion is on in {path}."
    ]
    assert reconcile(service, True, [*NAMES, "task"], find=find) == []  # refreshed silently
    assert "tk, tame, task" in path.read_text(encoding="utf-8")
    assert reconcile(service, False, NAMES, find=find) == [f"Tab completion removed from {path}."]
    assert BEGIN not in path.read_text(encoding="utf-8")
    assert reconcile(service, False, NAMES, find=find) == []


def test_block_keeps_the_rest_encoding_and_newlines(service: TaskService, tmp_path: Path) -> None:
    path = tmp_path / "ps" / "profile.ps1"
    path.parent.mkdir()
    path.write_bytes(codecs.BOM_UTF16_LE + "Set-Alias ll ls\r\n".encode("utf-16-le"))
    reconcile(service, True, NAMES, explicit=True, find=lambda: profiles_in(tmp_path))
    data = path.read_bytes()
    assert data.startswith(codecs.BOM_UTF16_LE)
    text = data.decode("utf-16")
    assert text.startswith("Set-Alias ll ls\r\n\r\n" + BEGIN + "\r\n")
    reconcile(service, False, NAMES)
    assert path.read_bytes().decode("utf-16") == "Set-Alias ll ls\r\n\r\n"


def test_blocked_execution_policy_writes_nothing(service: TaskService, tmp_path: Path) -> None:
    find = lambda: profiles_in(tmp_path, "Restricted")  # noqa: E731
    (message,) = reconcile(service, True, NAMES, find=find)
    assert "execution policy Restricted" in message
    assert reconcile(service, True, NAMES, find=find) == []  # told once
    assert not (tmp_path / "ps").exists()
    assert len(reconcile(service, True, NAMES, explicit=True, find=find)) == 1


def test_no_supported_shell(service: TaskService) -> None:
    assert reconcile(service, True, NAMES, explicit=True, find=list) == [
        "Tab completion: no supported shell found (PowerShell, or bash as your shell). "
        "See tk help completion."
    ]


# --- Through the CLI ------------------------------------------------------------------------


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Pretend stdout is a terminal; profiles live in ``tmp_path``."""
    monkeypatch.setattr(shellprofile, "is_terminal", lambda: True)
    monkeypatch.setattr(shellprofile, "discover", lambda: profiles_in(tmp_path))
    monkeypatch.setattr("tame.alias.installed", lambda: [])
    return tmp_path / "ps" / "profile.ps1"


def test_cli_tip_then_config_switch(capsys: Capture, terminal: Path) -> None:
    main(["config", "set", "kindness", "false"])
    assert main(["add", "x"]) == 0
    assert capsys.readouterr().out.splitlines()[-1].startswith("Tip: Tab completion")
    main(["list"])
    assert "Tip" not in capsys.readouterr().out
    main(["config", "set", "completion", "true"])
    out = capsys.readouterr().out
    assert (
        out.splitlines()[-1]
        == f"Tab completion enabled in {terminal}. Open a new terminal to use it."
    )
    assert BEGIN in terminal.read_text(encoding="utf-8")
    main(["config", "unset", "completion"])
    assert capsys.readouterr().out.splitlines()[-1] == f"Tab completion removed from {terminal}."


def test_cli_manual_edit_is_applied_on_next_command(
    capsys: Capture, terminal: Path, tame_home: Path
) -> None:
    main(["config", "set", "kindness", "false"])
    main(["config", "set", "completion", "true"])
    config = tame_home / "config.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace("completion = true", "completion = false"),
        encoding="utf-8",
    )
    capsys.readouterr()
    main(["version"])
    assert capsys.readouterr().out.splitlines()[-1] == f"Tab completion removed from {terminal}."


def test_cli_does_nothing_outside_a_terminal(capsys: Capture, tmp_path: Path) -> None:
    main(["add", "x"])
    main(["config", "set", "completion", "true"])
    assert "Tab completion" not in capsys.readouterr().out


# --- discover (fake shells only) ------------------------------------------------------


def test_discover_asks_powershell(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    monkeypatch.setattr(shellprofile.sys, "platform", "win32")
    monkeypatch.setattr(shellprofile, "_has_git_bash", lambda: False)
    monkeypatch.setattr(
        shellprofile.shutil, "which", lambda exe: exe if exe == "powershell" else None
    )
    asked: list[list[str]] = []

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        asked.append(argv)
        output = "C:/me/profile.ps1" + chr(10) + "RemoteSigned" + chr(10)
        return subprocess.CompletedProcess(argv, 0, output)

    monkeypatch.setattr(shellprofile.subprocess, "run", fake_run)
    assert real_discover() == [Profile("powershell", "C:/me/profile.ps1", "RemoteSigned")]
    assert asked[0][:2] == ["powershell", "-NoProfile"]


def test_discover_drops_inherited_module_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """tk run from pwsh must still find Windows PowerShell's profile, and vice versa."""
    import subprocess

    monkeypatch.setattr(shellprofile.sys, "platform", "win32")
    monkeypatch.setattr(shellprofile, "_has_git_bash", lambda: False)
    monkeypatch.setattr(shellprofile.shutil, "which", lambda exe: exe)
    monkeypatch.setenv("PSModulePath", r"C:\Program Files\PowerShell\7\Modules")
    monkeypatch.setenv("TAME_KEEP", "1")

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        env = kwargs["env"]
        assert isinstance(env, dict)
        broken = any(key.upper() == "PSMODULEPATH" for key in env)
        assert env["TAME_KEEP"] == "1"
        output = f"C:/me/{argv[0]}.ps1" + chr(10) + ("" if broken else "RemoteSigned")
        return subprocess.CompletedProcess(argv, 0, output)

    monkeypatch.setattr(shellprofile.subprocess, "run", fake_run)
    assert [p.path for p in real_discover()] == ["C:/me/powershell.ps1", "C:/me/pwsh.ps1"]


def test_discover_git_bash_on_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(shellprofile.sys, "platform", "win32")
    monkeypatch.setattr(shellprofile.shutil, "which", lambda exe: None)
    monkeypatch.setattr(shellprofile, "_has_git_bash", lambda: True)
    monkeypatch.setattr(shellprofile.Path, "home", lambda: tmp_path)
    assert real_discover() == [Profile("bash", str(tmp_path / ".bashrc"))]


def test_has_git_bash_finds_git_for_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "none"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "none"))
    git = tmp_path / "Git" / "cmd" / "git.exe"
    git.parent.mkdir(parents=True)
    git.touch()
    monkeypatch.setattr(shellprofile.shutil, "which", lambda exe: str(git))
    assert not shellprofile._has_git_bash()  # git alone, or WSL's bash.exe, is not enough
    (tmp_path / "Git" / "git-bash.exe").touch()
    assert shellprofile._has_git_bash()
    monkeypatch.setattr(shellprofile.shutil, "which", lambda exe: None)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))  # not on PATH: default install folder
    assert shellprofile._has_git_bash()


def test_bashrc_gets_lf_on_windows(
    monkeypatch: pytest.MonkeyPatch, service: TaskService, tmp_path: Path
) -> None:
    monkeypatch.setattr(shellprofile.sys, "platform", "win32")
    path = tmp_path / ".bashrc"
    reconcile(service, True, NAMES, explicit=True, find=lambda: [Profile("bash", str(path))])
    data = path.read_bytes()
    assert b"complete -o default -F _tame_complete tk tame" in data
    assert b"\r" not in data


def test_discover_bash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shellprofile.sys, "platform", "linux")
    monkeypatch.setenv("SHELL", "/bin/bash")
    assert [p.shell for p in real_discover()] == ["bash"]
    monkeypatch.setenv("SHELL", "/bin/zsh")
    assert real_discover() == []
