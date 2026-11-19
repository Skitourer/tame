"""Opt-in command aliases such as ``task`` (SPEC §1, §5). Never prints.

An alias is a small launcher script ("shim") in the directory where ``uv tool install``
puts its commands. It runs the current Python with ``-m tame``. A marker line tells
TAME's shims apart from other files, which are never overwritten or removed.
"""

import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from tame.errors import UsageError

MARKER = "tame alias shim"
"""Text present in every shim TAME writes."""

RESERVED = frozenset({"tame", "tk"})
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


@dataclass(frozen=True, slots=True)
class AliasResult:
    """Outcome of :func:`install`.

    Attributes:
        path: The shim file.
        on_path: Whether its directory is in ``PATH``.
        shadowed_by: Another command of that name found first in ``PATH``, if any.
    """

    path: Path
    on_path: bool
    shadowed_by: Path | None


def bin_dir() -> Path:
    """Return the directory of ``uv tool`` commands, following uv's rules.

    ``UV_TOOL_BIN_DIR``, else ``XDG_BIN_HOME``, else ``$XDG_DATA_HOME/../bin``, else
    ``~/.local/bin`` (on every OS).
    """
    if value := os.environ.get("UV_TOOL_BIN_DIR"):
        return Path(value)
    if value := os.environ.get("XDG_BIN_HOME"):
        return Path(value)
    if value := os.environ.get("XDG_DATA_HOME"):
        return Path(value).parent / "bin"
    return Path.home() / ".local" / "bin"


def shim_path(name: str, directory: Path | None = None) -> Path:
    """Return where the shim for ``name`` lives (``name.cmd`` on Windows).

    Raises:
        UsageError: If ``name`` is not a plain command name, or is ``tame``/``tk``.
    """
    if not _NAME_RE.fullmatch(name) or name.lower() in RESERVED:
        raise UsageError("error.alias_name", name=name)
    filename = f"{name}.cmd" if sys.platform == "win32" else name
    return (directory or bin_dir()) / filename


def shim_text() -> str:
    """Return the content of a shim running this Python with ``-m tame``."""
    python = sys.executable
    if sys.platform == "win32":
        return (
            f"@echo off\r\nrem {MARKER}: remove with 'tk alias remove'.\r\n"
            f'"{python}" -m tame %*\r\n'
        )
    return (
        f'#!/bin/sh\n# {MARKER}: remove with \'tk alias remove\'.\nexec "{python}" -m tame "$@"\n'
    )


def is_shim(path: Path) -> bool:
    """Return True if ``path`` is a shim written by TAME."""
    try:
        return MARKER in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def install(name: str, directory: Path | None = None) -> AliasResult:
    """Create (or refresh) the shim for ``name``.

    Raises:
        UsageError: If the name is invalid, a file not made by TAME is in the way, or
            the file cannot be written.
    """
    path = shim_path(name, directory)
    if path.exists() and not is_shim(path):
        raise UsageError("error.alias_exists", path=str(path))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(shim_text().encode("utf-8"))
        if sys.platform != "win32":
            path.chmod(0o755)
    except OSError as exc:
        raise UsageError("error.alias_io", path=str(path), detail=exc.strerror) from exc
    dirs = [Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    on_path = any(_same(d, path.parent) for d in dirs)
    found = shutil.which(name)
    shadowed = Path(found) if found and on_path and not _same(Path(found), path) else None
    return AliasResult(path=path, on_path=on_path, shadowed_by=shadowed)


def remove(name: str, directory: Path | None = None) -> Path:
    """Delete the shim for ``name`` and return its path.

    Raises:
        UsageError: If the name is invalid, there is no such shim, the file was not
            made by TAME, or it cannot be deleted.
    """
    path = shim_path(name, directory)
    if not path.exists():
        raise UsageError("error.alias_missing", name=name, path=str(path))
    if not is_shim(path):
        raise UsageError("error.alias_not_ours", path=str(path))
    try:
        path.unlink()
    except OSError as exc:
        raise UsageError("error.alias_io", path=str(path), detail=exc.strerror) from exc
    return path


def _same(a: Path, b: Path) -> bool:
    try:
        return os.path.normcase(a.resolve()) == os.path.normcase(b.resolve())
    except OSError:
        return False
