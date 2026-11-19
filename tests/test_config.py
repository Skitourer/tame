from pathlib import Path

import pytest

from tame.config import config_dir, data_dir


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Clear TAME_HOME and pin the user home directory."""
    monkeypatch.delenv("TAME_HOME")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def linux(monkeypatch: pytest.MonkeyPatch, home: Path) -> Path:
    monkeypatch.setattr("sys.platform", "linux")
    for var in ("APPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(var, raising=False)
    return home


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch, home: Path) -> Path:
    monkeypatch.setattr("sys.platform", "win32")
    return home


def test_tame_home_wins_for_both(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TAME_HOME", str(tmp_path))
    assert data_dir() == config_dir() == tmp_path


def test_windows_appdata(monkeypatch: pytest.MonkeyPatch, windows: Path) -> None:
    appdata = windows / "Roaming"
    monkeypatch.setenv("APPDATA", str(appdata))
    assert data_dir() == config_dir() == appdata / "tame"


def test_windows_without_appdata(monkeypatch: pytest.MonkeyPatch, windows: Path) -> None:
    monkeypatch.delenv("APPDATA", raising=False)
    assert data_dir() == windows / "AppData" / "Roaming" / "tame"


def test_linux_defaults(linux: Path) -> None:
    assert data_dir() == linux / ".local" / "share" / "tame"
    assert config_dir() == linux / ".config" / "tame"


def test_linux_ignores_appdata(monkeypatch: pytest.MonkeyPatch, linux: Path) -> None:
    monkeypatch.setenv("APPDATA", "/somewhere")
    assert data_dir() == linux / ".local" / "share" / "tame"


def test_linux_xdg_vars(monkeypatch: pytest.MonkeyPatch, linux: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(linux / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(linux / "conf"))
    assert data_dir() == linux / "data" / "tame"
    assert config_dir() == linux / "conf" / "tame"


@pytest.mark.parametrize("value", ["", "relative/dir"])
def test_linux_ignores_invalid_xdg(
    monkeypatch: pytest.MonkeyPatch, linux: Path, value: str
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", value)
    assert data_dir() == linux / ".local" / "share" / "tame"
