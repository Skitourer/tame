"""Directories and the ``config.toml`` settings file (SPEC §2, §7).

The file is created with commented defaults on first run. Users edit it by hand or with
``tk config``. Reading uses the standard ``tomllib``; writing uses ``tomlkit``, imported
lazily, so that comments and layout survive ``tk config set``.
"""

import math
import os
import re
import sys
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tame.core.urgency import Coefficients
from tame.errors import UsageError
from tame.i18n import available_languages, t

CONFIG_FILENAME = "config.toml"

_RETENTION_RE = re.compile(r"([1-9]\d*)([dwmy])")
_RETENTION_DAYS = {"d": 1, "w": 7, "m": 30, "y": 365}
_TRUE = frozenset({"true", "yes", "on", "1"})
_FALSE = frozenset({"false", "no", "off", "0"})


def data_dir() -> Path:
    r"""Return the directory holding ``tasks.db``.

    ``TAME_HOME`` if set; else ``%APPDATA%\tame`` on Windows; else
    ``$XDG_DATA_HOME/tame``, defaulting to ``~/.local/share/tame``.

    Returns:
        The directory path. It may not exist yet.
    """
    return _resolve("XDG_DATA_HOME", Path(".local") / "share")


def config_dir() -> Path:
    r"""Return the directory holding ``config.toml``.

    ``TAME_HOME`` if set; else ``%APPDATA%\tame`` on Windows; else
    ``$XDG_CONFIG_HOME/tame``, defaulting to ``~/.config/tame``.

    Returns:
        The directory path. It may not exist yet.
    """
    return _resolve("XDG_CONFIG_HOME", Path(".config"))


def config_path() -> Path:
    """Return the path of ``config.toml``."""
    return config_dir() / CONFIG_FILENAME


def _resolve(xdg_var: str, xdg_default: Path) -> Path:
    if home := os.environ.get("TAME_HOME"):
        return Path(home)
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        return (Path(appdata) if appdata else Path.home() / "AppData" / "Roaming") / "tame"
    # XDG Base Directory spec: ignore empty or relative values.
    xdg = os.environ.get(xdg_var, "")
    base = Path(xdg) if xdg and Path(xdg).is_absolute() else Path.home() / xdg_default
    return base / "tame"


class ConfigError(UsageError):
    """``config.toml`` is invalid, or a ``tk config`` request is."""


# --- Options ---------------------------------------------------------------------


def parse_retention(text: str) -> timedelta | None:
    """Parse an undo retention: ``forever`` (None) or ``<n><d|w|m|y>``, m = 30 d, y = 365 d.

    Raises:
        ValueError: If ``text`` is not a retention.
    """
    if text == "forever":
        return None
    if match := _RETENTION_RE.fullmatch(text):
        return timedelta(days=int(match[1]) * _RETENTION_DAYS[match[2]])
    raise ValueError(text)


def _check_language(value: Any) -> bool:
    return value in available_languages()


def _check_date_format(value: Any) -> bool:
    try:
        return bool(value) and bool(datetime(2026, 1, 2, tzinfo=UTC).strftime(value))
    except ValueError:
        return False


def _check_retention(value: Any) -> bool:
    try:
        parse_retention(value)
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class Option:
    """One setting.

    Attributes:
        key: Dotted name, ``section.name`` for options in a table.
        default: Default value; its type is the option's type.
        comment: Comment written above the option in a new file.
        expected: i18n key describing valid values, for error messages.
        check: Extra validation beyond the type.
    """

    key: str
    default: bool | int | float | str
    comment: str
    expected: str
    check: Callable[[Any], bool] | None = field(default=None, compare=False)


_COEFFICIENTS = Coefficients()
OPTIONS: tuple[Option, ...] = (
    Option(
        "language",
        "en",
        "User interface language.",
        "setting.expected.language",
        _check_language,
    ),
    Option(
        "confirm_threshold",
        3,
        "Ask before done/delete/modify change more tasks than this (delete always asks).",
        "setting.expected.count",
        lambda value: value >= 0,
    ),
    Option(
        "date_format",
        "%Y-%m-%d",
        "How dates are shown (Python strftime codes).",
        "setting.expected.date_format",
        _check_date_format,
    ),
    Option("color", True, "Colored output in the terminal.", "setting.expected.bool"),
    Option(
        "kindness",
        True,
        "Now and then, a kind word about the people around you.",
        "setting.expected.bool",
    ),
    Option(
        "default_command",
        "list",
        "What tk alone (or tk <filter>) runs: list or next.",
        "setting.expected.default_command",
        lambda value: value in ("list", "next"),
    ),
    Option(
        "next_limit",
        10,
        "How many tasks next shows.",
        "setting.expected.positive",
        lambda value: value >= 1,
    ),
    Option(
        "completion",
        False,
        "Tab completion in your shell profile (PowerShell, bash), for new terminals.",
        "setting.expected.bool",
    ),
    Option(
        "undo.retention",
        "3m",
        "Keep undo history this long: forever, or <n>d/w/m/y (m = 30 days, y = 365 days).",
        "setting.expected.retention",
        _check_retention,
    ),
    *(
        Option(
            f"urgency.{name}",
            getattr(_COEFFICIENTS, name),
            f"Urgency weight: {comment}.",
            "setting.expected.number",
            math.isfinite,
        )
        for name, comment in (
            ("pri_H", "priority H"),
            ("pri_M", "priority M"),
            ("pri_L", "priority L"),
            ("due", "due date, x0.2 (14+ days ahead) to x1.0 (7+ days overdue)"),
            ("age", "age, x0 (new) to x1.0 (1 year old)"),
            ("tags", "task has tags"),
            ("project", "task has a project"),
            ("blocked", "waits for another pending task (depends)"),
            ("blocking", "another pending task waits for it"),
        )
    ),
)
OPTIONS_BY_KEY: Mapping[str, Option] = {option.key: option for option in OPTIONS}


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated settings.

    Attributes:
        values: Value of every option, by dotted key.
    """

    values: Mapping[str, Any] = field(
        default_factory=lambda: {option.key: option.default for option in OPTIONS}
    )

    @property
    def language(self) -> str:
        """UI language code."""
        return str(self.values["language"])

    @property
    def confirm_threshold(self) -> int:
        """Task count above which write commands ask for confirmation."""
        return int(self.values["confirm_threshold"])

    @property
    def date_format(self) -> str:
        """Format of dates, in strftime codes."""
        return str(self.values["date_format"])

    @property
    def color(self) -> bool:
        """Whether terminal output may use colors."""
        return bool(self.values["color"])

    @property
    def kindness(self) -> bool:
        """Whether kind words may appear now and then."""
        return bool(self.values["kindness"])

    @property
    def default_command(self) -> str:
        """Command run when none is typed: ``list`` or ``next``."""
        return str(self.values["default_command"])

    @property
    def next_limit(self) -> int:
        """How many tasks ``next`` shows."""
        return int(self.values["next_limit"])

    @property
    def completion(self) -> bool:
        """Whether TAME keeps its Tab completion block in the shell profiles."""
        return bool(self.values["completion"])

    @property
    def undo_retention(self) -> timedelta | None:
        """How long undo history is kept; None = forever."""
        return parse_retention(str(self.values["undo.retention"]))

    @property
    def urgency(self) -> Coefficients:
        """Urgency coefficients."""
        prefix = "urgency."
        return Coefficients(
            **{
                key.removeprefix(prefix): float(value)
                for key, value in self.values.items()
                if key.startswith(prefix)
            }
        )


def coerce(option: Option, value: Any) -> bool | int | float | str:
    """Return ``value`` as a valid value of ``option``.

    Raises:
        ValueError: If ``value`` has the wrong type or fails the option's check.
    """
    kind = type(option.default)
    if kind is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if type(value) is not kind or (option.check is not None and not option.check(value)):
        raise ValueError(value)
    result: bool | int | float | str = value
    return result


def parse_text(option: Option, text: str) -> bool | int | float | str:
    """Parse ``text`` typed on the command line as a value of ``option``.

    Raises:
        ValueError: If ``text`` is not a valid value.
    """
    kind = type(option.default)
    value: bool | int | float | str
    if kind is bool:
        word = text.strip().lower()
        if word not in _TRUE | _FALSE:
            raise ValueError(text)
        value = word in _TRUE
    elif kind is int:
        value = int(text)
    elif kind is float:
        value = float(text)
    else:
        value = text
    return coerce(option, value)


def format_value(value: Any) -> str:
    """Format a setting value as TOML (``"en"``, ``3``, ``true``, ``6.0``)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return repr(value)


def invalid_value(option: Option, value: Any, path: Path | None = None) -> ConfigError:
    """Return the error for an invalid ``value`` of ``option`` (in file ``path``)."""
    return ConfigError(
        "error.config_invalid_value",
        path=str(path or config_path()),
        name=option.key,
        value=format_value(value),
        expected=t(option.expected, languages=", ".join(available_languages())),
    )


# --- File -------------------------------------------------------------------------


def default_config_text() -> str:
    """Return the content of a new ``config.toml``: every option, commented."""
    lines = [
        "# TAME settings. Edit by hand or with `tk config set <key> <value>`.",
        "# A missing option uses its default value.",
    ]
    section = ""
    for option in OPTIONS:
        table, _, name = option.key.rpartition(".")
        if table != section:
            section = table
            lines += ["", f"[{table}]"]
        lines += ["", f"# {option.comment}", f"{name} = {format_value(option.default)}"]
    return "\n".join(lines) + "\n"


def ensure_config_file(path: Path | None = None) -> Path:
    """Create ``config.toml`` with commented defaults if missing; return its path.

    Raises:
        ConfigError: If the file cannot be created.
    """
    path = path or config_path()
    if not path.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(default_config_text(), encoding="utf-8")
        except OSError as exc:
            raise ConfigError("error.config_io", path=str(path), detail=str(exc)) from exc
    return path


def load_settings(path: Path | None = None) -> Settings:
    """Read ``config.toml``, creating it with defaults if missing.

    Args:
        path: Config file; defaults to :func:`config_path`.

    Raises:
        ConfigError: If the file cannot be written or read, is not valid TOML, has an
            unknown option or an invalid value.
    """
    path = ensure_config_file(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError("error.config_io", path=str(path), detail=str(exc)) from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError("error.config_syntax", path=str(path), detail=str(exc)) from exc
    values = dict(Settings().values)
    for key, value in _flatten(data):
        if (option := OPTIONS_BY_KEY.get(key)) is None:
            raise ConfigError("error.config_unknown_key", path=str(path), name=key)
        try:
            values[key] = coerce(option, value)
        except ValueError:
            raise invalid_value(option, value, path) from None
    return Settings(values)


def configured_language(path: Path | None = None) -> str:
    """Return the ``language`` setting, or the default if it cannot be read.

    Never raises and never creates the file: the language is needed before anything
    else, including to report a broken settings file.
    """
    default = str(OPTIONS_BY_KEY["language"].default)
    try:
        data = tomllib.loads((path or config_path()).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return default
    value = data.get("language")
    return value if isinstance(value, str) and _check_language(value) else default


def configured_color(path: Path | None = None) -> bool:
    """Return the ``color`` setting, or the default if it cannot be read.

    Never raises and never creates the file: errors about the file itself are shown
    with it.
    """
    default = bool(OPTIONS_BY_KEY["color"].default)
    try:
        data = tomllib.loads((path or config_path()).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return default
    value = data.get("color")
    return value if isinstance(value, bool) else default


def _flatten(data: Mapping[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    for name, value in data.items():
        key = f"{prefix}{name}"
        if isinstance(value, dict) and not prefix:
            items += _flatten(value, f"{key}.")
        else:
            items.append((key, value))
    return items


def option(key: str) -> Option:
    """Return the option named ``key``.

    Raises:
        ConfigError: If there is no such option.
    """
    if (found := OPTIONS_BY_KEY.get(key)) is None:
        raise ConfigError("error.config_unknown_option", name=key)
    return found


def write_value(key: str, value: bool | int | float | str, path: Path | None = None) -> None:
    """Set ``key`` to ``value`` in ``config.toml``, keeping comments and layout.

    Raises:
        ConfigError: If there is no such option or the file cannot be read or written.
    """
    import tomlkit
    from tomlkit.exceptions import TOMLKitError

    found = option(key)
    path = path or config_path()
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else default_config_text()
        doc = tomlkit.parse(text)
        table, _, name = found.key.rpartition(".")
        container: Any = doc
        if table:
            if table not in doc:
                doc[table] = tomlkit.table()
            container = doc[table]
        container[name] = value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    except OSError as exc:
        raise ConfigError("error.config_io", path=str(path), detail=str(exc)) from exc
    except TOMLKitError as exc:
        raise ConfigError("error.config_syntax", path=str(path), detail=str(exc)) from exc
