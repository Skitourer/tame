"""Command-line parsing.

Step-2 subset of the SPEC §4 grammar: the command must come first (or be absent,
meaning ``list``), and ``add`` understands ``project:``, ``pri:``/``priority:``,
``+tag`` and ``--``. Filters and the TW-order grammar arrive in roadmap step 3.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from tame.errors import UsageError

COMMANDS = ("add", "list", "version")
"""Implemented command names (never translated)."""

_ATTR_ALIASES = {"pri": "priority"}
_ATTR_RE = re.compile(r"([a-z]+):(.*)", re.DOTALL)


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    """A resolved command and its remaining tokens."""

    name: str
    args: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AddArgs:
    """Arguments of ``add``. Empty ``attr:`` values become None."""

    description: str
    project: str | None = None
    tags: tuple[str, ...] = ()
    priority: str | None = None


def resolve_command(token: str) -> str:
    """Return the command named by ``token``: exact name or unique prefix (rule 1).

    Raises:
        UsageError: If no command, or several, match.
    """
    if token in COMMANDS:
        return token
    matches = [name for name in COMMANDS if token and name.startswith(token)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise UsageError("error.ambiguous_command", name=token, candidates=", ".join(matches))
    raise UsageError("error.unknown_command", name=token)


def parse_command(argv: Sequence[str]) -> ParsedCommand:
    """Split ``argv`` into a command and its arguments; no tokens means ``list``.

    Raises:
        UsageError: If the first token is not a command.
    """
    if not argv:
        return ParsedCommand("list")
    return ParsedCommand(resolve_command(argv[0]), tuple(argv[1:]))


def parse_add(tokens: Sequence[str]) -> AddArgs:
    """Parse the tokens following ``add`` (rule 3: never a filter).

    Raises:
        UsageError: On an unknown ``attr:`` (rule 6).
    """
    words: list[str] = []
    tags: list[str] = []
    attrs: dict[str, str | None] = {"project": None, "priority": None}
    for index, token in enumerate(tokens):
        if token == "--":  # Rule 5: the rest is description.
            words.extend(tokens[index + 1 :])
            break
        if len(token) > 1 and token.startswith("+"):
            tags.append(token[1:])
            continue
        if match := _ATTR_RE.fullmatch(token):
            name = _ATTR_ALIASES.get(match[1], match[1])
            if name not in attrs:
                raise UsageError("error.unknown_attribute", name=match[1])  # Rule 6.
            attrs[name] = match[2] or None
            continue
        words.append(token)
    return AddArgs(
        description=" ".join(words),
        project=attrs["project"],
        tags=tuple(tags),
        priority=attrs["priority"],
    )
