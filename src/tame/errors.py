"""Typed errors raised by TAME and their process exit codes (SPEC §5).

Errors carry an i18n key and its parameters instead of a rendered message, so
``core`` and ``storage`` never deal with UI text; the CLI translates them with ``t()``.
"""

from enum import IntEnum
from typing import ClassVar


class ExitCode(IntEnum):
    """Process exit codes."""

    OK = 0
    USAGE = 1
    NO_MATCH = 2
    INTERNAL = 3


class TameError(Exception):
    """Base class of all TAME errors.

    Args:
        key: i18n key of the message (see ``locales/en.toml``).
        **params: Values substituted into the message.
    """

    exit_code: ClassVar[ExitCode] = ExitCode.INTERNAL

    def __init__(self, key: str, **params: object) -> None:
        super().__init__(key)
        self.key = key
        self.params = params


class UsageError(TameError):
    """The command line is invalid."""

    exit_code = ExitCode.USAGE


class ValidationError(UsageError):
    """A value given by the user is invalid (bad tag, empty description...)."""


class NoMatchError(TameError):
    """No task matches the request."""

    exit_code = ExitCode.NO_MATCH


class StorageError(TameError):
    """The database cannot be opened, migrated or written."""
