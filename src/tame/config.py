"""Data and config directory resolution (SPEC §2).

The ``config.toml`` file itself comes in roadmap step 7.
"""

import os
import sys
from pathlib import Path


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
