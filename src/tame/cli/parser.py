"""Command-line grammar (SPEC §4).

::

    tk [filter] <cmd> [args]   # TW order (canonical)
    tk <cmd> [filter] [args]   # classic order (tolerated)
    tk [filter]                # = tk [filter] list

Comments cite the SPEC §4 rule numbers. Full reference: ``docs/grammar.md``.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from tame.core.filters import NONE, Filter
from tame.core.models import Priority, Status, check_project, check_tag, parse_priority
from tame.errors import UsageError, ValidationError

COMMANDS = (
    "add",
    "alias",
    "delete",
    "done",
    "export",
    "help",
    "import",
    "info",
    "list",
    "modify",
    "undo",
    "version",
)
"""V1 command names (never translated)."""

FILTER_COMMANDS = frozenset({"list", "done", "delete", "modify", "info", "export"})
"""Commands that accept a filter."""

_ARGLESS_COMMANDS = frozenset({"list", "done", "delete", "info", "export"})
"""Filter commands without arguments: their trailing tokens extend the filter."""

_ATTR_ALIASES = {"pri": "priority"}
_ATTR_RE = re.compile(r"([a-z]+(?:\.[a-z]+)?):(.*)", re.DOTALL)
_IDS_RE = re.compile(r"\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*")
_UUID_DASHED_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f-]*", re.IGNORECASE)
_UUID_HEX_RE = re.compile(r"[0-9a-f]{8,}", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    """A command with its raw filter tokens and argument tokens."""

    name: str
    filter: tuple[str, ...] = ()
    args: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AddArgs:
    """Arguments of ``add``. Empty ``attr:`` values become None."""

    description: str
    project: str | None = None
    tags: tuple[str, ...] = ()
    priority: str | None = None


def match_command(token: str) -> str | None:
    """Return the command named by ``token`` (exact name or unique prefix), else None.

    Raises:
        UsageError: If ``token`` is a prefix of several commands.
    """
    if token in COMMANDS:
        return token
    matches = [name for name in COMMANDS if token and name.startswith(token)]
    if len(matches) > 1:
        raise UsageError("error.ambiguous_command", name=token, candidates=", ".join(matches))
    return matches[0] if matches else None


def parse_command(argv: Sequence[str]) -> ParsedCommand:
    """Split ``argv`` into command, filter tokens and argument tokens.

    Raises:
        UsageError: On an ambiguous command, or a filter given to a command without one.
    """
    tokens = tuple(argv)
    # Rule 1: the first token naming a command is the command; `--` stops the search (rule 5).
    found: tuple[int, str] | None = None
    for index, token in enumerate(tokens):
        if token == "--":
            break
        if (name := match_command(token)) is not None:
            found = index, name
            break
    if found is None:  # No command: `tk [filter]` = list.
        return ParsedCommand("list", filter=tokens)

    position, name = found

    before, after = tokens[:position], tokens[position + 1 :]
    if name == "add":  # Rule 3: everything after `add` is the new task, never a filter.
        _check_no_filter(name, before)
        return ParsedCommand(name, args=after)
    if before:  # Rule 2: tokens before the command are the filter.
        filter_tokens, args = before, after
    else:  # Rule 4: classic order; leading filter-like tokens are the filter.
        is_filter = _is_id_token if name == "modify" else _is_filter_token
        count = next((i for i, tok in enumerate(after) if not is_filter(tok)), len(after))
        filter_tokens, args = after[:count], after[count:]
    if name in _ARGLESS_COMMANDS:
        filter_tokens, args = filter_tokens + args, ()
    _check_no_filter(name, filter_tokens)
    return ParsedCommand(name, filter=filter_tokens, args=args)


def _check_no_filter(name: str, filter_tokens: tuple[str, ...]) -> None:
    # Rule 7.
    if filter_tokens and name not in FILTER_COMMANDS:
        raise UsageError("error.filter_not_allowed", command=name)


def _is_id_token(token: str) -> bool:
    return bool(
        _IDS_RE.fullmatch(token)
        or _UUID_DASHED_RE.fullmatch(token)
        or _UUID_HEX_RE.fullmatch(token)
    )


def _is_filter_token(token: str) -> bool:
    return (
        _is_id_token(token)
        or (len(token) > 1 and token[0] in "+-")
        or _ATTR_RE.fullmatch(token) is not None
    )


def parse_filter(tokens: Sequence[str]) -> Filter:
    """Build a :class:`Filter` from filter tokens (SPEC §4 filter table).

    Raises:
        UsageError: On an unknown ``attr:`` (rule 6) or a malformed id range.
        ValidationError: On an invalid tag, project, priority or status.
    """
    ids: set[int] = set()
    uuids: list[str] = []
    tags_in: set[str] = set()
    tags_out: set[str] = set()
    project: str | None = None
    priority: Priority | Literal[""] | None = None
    status: Status | None = None
    words: list[str] = []
    for index, token in enumerate(tokens):
        if token == "--":  # Rule 5: the rest are plain words.
            words.extend(tokens[index + 1 :])
            break
        if _UUID_DASHED_RE.fullmatch(token):
            uuids.append(token.lower().replace("-", ""))
        elif _IDS_RE.fullmatch(token):
            ids |= _parse_ids(token)
        elif _UUID_HEX_RE.fullmatch(token):
            uuids.append(token.lower())
        elif len(token) > 1 and token[0] == "+":
            tags_in.add(check_tag(token[1:]))
        elif len(token) > 1 and token[0] == "-":
            tags_out.add(check_tag(token[1:]))
        elif match := _ATTR_RE.fullmatch(token):
            name, value = _ATTR_ALIASES.get(match[1], match[1]), match[2]
            if name == "project":
                project = check_project(value) if value else NONE
            elif name == "priority":
                priority = parse_priority(value) if value else NONE
            elif name == "status":
                status = _parse_status(value)
            else:
                raise UsageError("error.unknown_attribute", name=match[1])  # Rule 6.
        else:
            words.append(token)
    return Filter(
        ids=frozenset(ids),
        uuid_prefixes=tuple(uuids),
        tags_in=frozenset(tags_in),
        tags_out=frozenset(tags_out),
        project=project,
        priority=priority,
        status=status,
        words=tuple(words),
    )


def _parse_ids(token: str) -> set[int]:
    ids: set[int] = set()
    for part in token.split(","):
        low, _, high = part.partition("-")
        first, last = int(low), int(high or low)
        if first > last:
            raise UsageError("error.invalid_id_range", token=part)
        ids.update(range(first, last + 1))
    return ids


def _parse_status(value: str) -> Status:
    try:
        return Status(value.lower())
    except ValueError:
        raise ValidationError("error.invalid_status", value=value) from None


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
