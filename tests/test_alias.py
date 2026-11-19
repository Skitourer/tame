import os
import subprocess
import sys
from pathlib import Path

import pytest

from tame import __version__, alias
from tame.errors import UsageError

WINDOWS = sys.platform == "win32"


@pytest.fixture
def bin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty uv tool bin dir, in PATH."""
    directory = tmp_path / "bin"
    monkeypatch.setenv("UV_TOOL_BIN_DIR", str(directory))
    monkeypatch.setenv("PATH", str(directory) + os.pathsep + os.environ.get("PATH", ""))
    return directory


def shim(directory: Path, name: str = "task") -> Path:
    return directory / (f"{name}.cmd" if WINDOWS else name)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"UV_TOOL_BIN_DIR": "/a", "XDG_BIN_HOME": "/b", "XDG_DATA_HOME": "/c/share"}, "/a"),
        ({"XDG_BIN_HOME": "/b", "XDG_DATA_HOME": "/c/share"}, "/b"),
        ({"XDG_DATA_HOME": "/c/share"}, "/c/bin"),
    ],
)
def test_bin_dir_follows_uv(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], expected: str
) -> None:
    for var in ("UV_TOOL_BIN_DIR", "XDG_BIN_HOME", "XDG_DATA_HOME"):
        monkeypatch.delenv(var, raising=False)
    for var, value in env.items():
        monkeypatch.setenv(var, value)
    assert alias.bin_dir() == Path(expected)


def test_bin_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("UV_TOOL_BIN_DIR", "XDG_BIN_HOME", "XDG_DATA_HOME"):
        monkeypatch.delenv(var, raising=False)
    assert alias.bin_dir() == Path.home() / ".local" / "bin"


@pytest.mark.parametrize("name", ["tame", "TK", "", "-x", "a b", "a/b", "a.cmd", "é"])
def test_invalid_names(name: str, bin_dir: Path) -> None:
    with pytest.raises(UsageError) as exc:
        alias.install(name)
    assert exc.value.key == "error.alias_name"


def test_install_writes_a_marked_shim(bin_dir: Path) -> None:
    result = alias.install("task")
    assert result.path == shim(bin_dir)
    assert alias.is_shim(result.path)
    assert sys.executable in result.path.read_text(encoding="utf-8")
    assert result.on_path
    if not WINDOWS:
        assert os.access(result.path, os.X_OK)


def test_shim_runs_tame(bin_dir: Path) -> None:
    path = alias.install("task").path
    argv = ["cmd", "/c", str(path), "version"] if WINDOWS else [str(path), "version"]
    out = subprocess.run(argv, capture_output=True, text=True, check=True).stdout
    assert out.startswith(f"tame {__version__} ")


def test_install_is_idempotent(bin_dir: Path) -> None:
    alias.install("task")
    assert alias.install("task").path == shim(bin_dir)


def test_install_never_overwrites_other_files(bin_dir: Path) -> None:
    bin_dir.mkdir()
    shim(bin_dir).write_text("someone else's", encoding="utf-8")
    with pytest.raises(UsageError) as exc:
        alias.install("task")
    assert exc.value.key == "error.alias_exists"
    assert shim(bin_dir).read_text(encoding="utf-8") == "someone else's"


def test_install_reports_dir_not_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "elsewhere"))
    result = alias.install("task", tmp_path / "bin")
    assert (result.on_path, result.shadowed_by) == (False, None)


def test_install_reports_shadowing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = tmp_path / "first"
    first.mkdir()
    other = shim(first)
    other.write_text("@echo other\n" if WINDOWS else "#!/bin/sh\necho other\n")
    other.chmod(0o755)
    monkeypatch.setenv("PATH", os.pathsep.join([str(first), str(tmp_path / "bin")]))
    result = alias.install("task", tmp_path / "bin")
    assert result.on_path
    assert result.shadowed_by is not None
    assert result.shadowed_by.parent == first


def test_remove(bin_dir: Path) -> None:
    path = alias.install("task").path
    assert alias.remove("task") == path
    assert not path.exists()
    with pytest.raises(UsageError) as exc:
        alias.remove("task")
    assert exc.value.key == "error.alias_missing"


def test_remove_never_deletes_other_files(bin_dir: Path) -> None:
    bin_dir.mkdir()
    shim(bin_dir).write_text("someone else's", encoding="utf-8")
    with pytest.raises(UsageError) as exc:
        alias.remove("task")
    assert exc.value.key == "error.alias_not_ours"
    assert shim(bin_dir).exists()
