import tomllib
from datetime import timedelta
from pathlib import Path

import pytest

from tame.config import (
    OPTIONS,
    OPTIONS_BY_KEY,
    ConfigError,
    Settings,
    config_dir,
    data_dir,
    default_config_text,
    format_value,
    load_settings,
    parse_retention,
    parse_text,
    write_value,
)
from tame.core.urgency import Coefficients


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


# --- settings file ------------------------------------------------------------------


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "sub" / "config.toml"


def test_first_load_creates_commented_defaults(path: Path) -> None:
    assert load_settings(path) == Settings()
    text = path.read_text(encoding="utf-8")
    assert text == default_config_text()
    assert "# Keep undo history this long" in text
    assert "[undo]\n\n# Keep undo history this long: forever, or <n>d/w/m/y" in text


def test_default_text_holds_every_option_with_its_default() -> None:
    data = tomllib.loads(default_config_text())
    flat = {f"{k}.{n}": v for k, t in data.items() if isinstance(t, dict) for n, v in t.items()}
    flat |= {k: v for k, v in data.items() if not isinstance(v, dict)}
    assert flat == {option.key: option.default for option in OPTIONS}


def test_spec_defaults() -> None:
    settings = Settings()
    assert (settings.language, settings.confirm_threshold) == ("en", 3)
    assert (settings.date_format, settings.color) == ("%Y-%m-%d", True)
    assert settings.undo_retention == timedelta(days=90)
    assert settings.urgency == Coefficients()


def test_missing_options_use_defaults(path: Path) -> None:
    path.parent.mkdir()
    path.write_text("confirm_threshold = 10\n[urgency]\ndue = 5\n", encoding="utf-8")
    settings = load_settings(path)
    assert settings.confirm_threshold == 10
    assert settings.urgency == Coefficients(due=5.0)
    assert settings.color is True


@pytest.mark.parametrize(
    ("text", "key", "params"),
    [
        ("colour = true", "error.config_unknown_key", {"name": "colour"}),
        ("[urgency]\nfoo = 1", "error.config_unknown_key", {"name": "urgency.foo"}),
        ("[undo.deep]\nx = 1", "error.config_unknown_key", {"name": "undo.deep"}),
        ("color = 1", "error.config_invalid_value", {"name": "color", "value": "1"}),
        ("confirm_threshold = -1", "error.config_invalid_value", {"name": "confirm_threshold"}),
        ("confirm_threshold = 2.5", "error.config_invalid_value", {"name": "confirm_threshold"}),
        ('language = "xx"', "error.config_invalid_value", {"name": "language"}),
        ('date_format = ""', "error.config_invalid_value", {"name": "date_format"}),
        ('[undo]\nretention = "3 months"', "error.config_invalid_value", {}),
        ('[urgency]\ndue = "high"', "error.config_invalid_value", {"name": "urgency.due"}),
        ("color = ", "error.config_syntax", {}),
    ],
)
def test_invalid_file(path: Path, text: str, key: str, params: dict[str, str]) -> None:
    path.parent.mkdir()
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_settings(path)
    assert exc.value.key == key
    assert exc.value.params["path"] == str(path)
    assert params.items() <= exc.value.params.items()


@pytest.mark.parametrize(
    ("text", "days"),
    [("forever", None), ("1d", 1), ("2w", 14), ("3m", 90), ("1y", 365)],
)
def test_parse_retention(text: str, days: int | None) -> None:
    expected = None if days is None else timedelta(days=days)
    assert parse_retention(text) == expected


@pytest.mark.parametrize("text", ["", "0d", "3", "3M", "1h", "never", "-1d"])
def test_parse_retention_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        parse_retention(text)


@pytest.mark.parametrize(
    ("key", "text", "value"),
    [
        ("color", "false", False),
        ("color", "On", True),
        ("confirm_threshold", "0", 0),
        ("urgency.due", "8", 8.0),
        ("urgency.pri_H", "-1.5", -1.5),
        ("date_format", "%d/%m/%Y", "%d/%m/%Y"),
        ("undo.retention", "forever", "forever"),
    ],
)
def test_parse_text(key: str, text: str, value: object) -> None:
    result = parse_text(OPTIONS_BY_KEY[key], text)
    assert result == value
    assert type(result) is type(value)


@pytest.mark.parametrize(
    ("key", "text"),
    [("color", "maybe"), ("confirm_threshold", "x"), ("urgency.due", "inf"), ("language", "xx")],
)
def test_parse_text_invalid(key: str, text: str) -> None:
    with pytest.raises(ValueError):
        parse_text(OPTIONS_BY_KEY[key], text)


def test_write_value_keeps_comments_and_other_values(path: Path) -> None:
    path.parent.mkdir()
    path.write_text("# mine\ncolor = false # keep me\n", encoding="utf-8")
    write_value("urgency.due", 8.0, path)
    write_value("confirm_threshold", 5, path)
    text = path.read_text(encoding="utf-8")
    assert "# mine" in text
    assert "# keep me" in text
    settings = load_settings(path)
    assert (settings.color, settings.confirm_threshold, settings.urgency.due) == (False, 5, 8.0)


def test_write_value_creates_file(path: Path) -> None:
    write_value("color", False, path)
    assert load_settings(path).color is False
    assert "# Colored output" in path.read_text(encoding="utf-8")


def test_write_value_unknown_option(path: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        write_value("nope", 1, path)
    assert exc.value.key == "error.config_unknown_option"


@pytest.mark.parametrize(
    ("value", "text"),
    [(True, "true"), (3, "3"), (6.0, "6.0"), ("en", '"en"'), ('a"b\\', '"a\\"b\\\\"')],
)
def test_format_value(value: object, text: str) -> None:
    assert format_value(value) == text
