"""Shell completion: the scripts ``tk completion`` prints, and the candidates (SPEC §5).

The scripts call the hidden ``tk _complete _<current> [words before it...]``; the
current word is prefixed with ``_`` so that an empty one survives Windows PowerShell 5.1,
which drops empty arguments to native commands. This module must stay light: it runs
on every Tab press, so it never imports rich or tomlkit.
"""

import sqlite3
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from tame.cli.parser import COMMANDS, match_command
from tame.core.models import VIRTUAL_TAGS, Priority, Status
from tame.core.recurrence import NAMED_PERIODS
from tame.errors import UsageError

SHELLS = ("powershell", "bash")
"""Shells ``tk completion`` has a script for."""

COMPLETE_COMMAND = "_complete"
"""Hidden command the scripts call."""

DATE_KEYWORDS = (
    "today",
    "tomorrow",
    "yesterday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "mon",
    "tue",
    "wed",
    "thu",
    "fri",
    "sat",
    "sun",
    "eow",
    "eom",
    "eoy",
)
_FILTER_ATTRS = ("project:", "pri:", "status:", "recur:", "due.before:", "due.after:")
_MOD_ATTRS = ("project:", "pri:", "due:", "wait:", "depends:", "recur:", "until:")
_DATE_ATTRS = frozenset({"due", "wait", "until", "due.before", "due.after"})
_MOD_COMMANDS = frozenset({"add", "modify"})
_TEXT_COMMANDS = frozenset({"import", "annotate", "denotate"})
_CONFIG_SUBCOMMANDS = ("get", "set", "unset", "path", "edit")
_HELP_TOPICS = (
    "filters",
    "dates",
    "urgency",
    "security",
    "settings",
    "tour",
    "license",
    "credits",
)


class Data:
    """Tags and projects of pending tasks, read from the database only when needed.

    Args:
        db_path: The task database; it is opened read-only and never created.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._cache: dict[str, list[str]] = {}

    def tags(self) -> list[str]:
        """Tags of pending tasks, sorted."""
        return self._query(
            "SELECT DISTINCT tag FROM task_tags JOIN tasks USING (uuid) "
            "WHERE status = 'pending' ORDER BY tag"
        )

    def projects(self) -> list[str]:
        """Projects of pending tasks, sorted."""
        return self._query(
            "SELECT DISTINCT project FROM tasks "
            "WHERE status = 'pending' AND project IS NOT NULL ORDER BY project"
        )

    def _query(self, sql: str) -> list[str]:
        if sql not in self._cache:
            self._cache[sql] = []
            if self._db_path.is_file():
                try:
                    uri = self._db_path.resolve().as_uri() + "?mode=ro"
                    with sqlite3.connect(uri, uri=True) as conn:
                        self._cache[sql] = [str(row[0]) for row in conn.execute(sql)]
                except sqlite3.Error:
                    pass
        return self._cache[sql]


def candidates(before: Sequence[str], current: str, data: Data) -> list[str]:
    """Return the completions of ``current``, given the words typed before it.

    Args:
        before: Words after the program name and before the current one.
        current: The (possibly empty) word being completed.
        data: Tags and projects of the user's tasks.

    Returns:
        Full tokens starting with ``current``, without duplicates, in a stable order.
    """
    if "--" in before:
        return []
    position, name = _command(before)
    args = list(before[position + 1 :]) if name else []
    match name:
        case "help":
            options: Iterable[str] = _help(args)
        case "config":
            options = _config(args)
        case "alias":
            options = () if args else ("install", "remove")
        case "completion":
            options = () if args else SHELLS
        case "undo" | "version":
            options = ()
        case _ if name in _TEXT_COMMANDS:
            options = ()
        case _:
            mods = name in _MOD_COMMANDS
            options = _token(current, data, mods=mods, first=name is None)
    seen: dict[str, None] = {}
    for option in options:
        if option.startswith(current):
            seen.setdefault(option)
    return list(seen)


def _command(before: Sequence[str]) -> tuple[int, str | None]:
    """Return the position and name of the command among ``before``, if any."""
    for index, word in enumerate(before):
        try:
            if (name := match_command(word)) is not None:
                return index, name
        except UsageError:
            continue
    return -1, None


def _help(args: Sequence[str]) -> Iterable[str]:
    if not args:
        return (*COMMANDS, *_HELP_TOPICS)
    if list(args) == ["config"]:
        from tame.config import OPTIONS

        return [option.key for option in OPTIONS]
    return ()


def _config(args: Sequence[str]) -> Iterable[str]:
    from tame.config import OPTIONS, OPTIONS_BY_KEY

    match args:
        case ():
            return _CONFIG_SUBCOMMANDS
        case ("get" | "set" | "unset",):
            return [option.key for option in OPTIONS]
        case ("set", key) if (option := OPTIONS_BY_KEY.get(key)) is not None:
            if key == "language":
                from tame.i18n import available_languages

                return available_languages()
            if key == "default_command":
                return ("list", "next")
            if isinstance(option.default, bool):
                return ("true", "false")
    return ()


def _token(current: str, data: Data, *, mods: bool, first: bool) -> Iterable[str]:
    """Completions of a filter or mods token: tags, ``attr:value``, attribute names."""
    if current[:1] in ("+", "-"):
        sign = current[0]
        tags = data.tags() if mods else [*data.tags(), *sorted(VIRTUAL_TAGS)]
        return [sign + tag for tag in tags]
    if ":" in current:
        attr, _ = current.split(":", 1)
        return [f"{attr}:{value}" for value in _values(attr, data)]
    attrs = _MOD_ATTRS if mods else _FILTER_ATTRS
    return [*COMMANDS, *attrs] if first else attrs


def _values(attr: str, data: Data) -> Iterable[str]:
    values: dict[str, Callable[[], Iterable[str]]] = {
        "project": data.projects,
        "pri": lambda: [p.value for p in Priority],
        "priority": lambda: [p.value for p in Priority],
        "status": lambda: [*(s.value for s in Status), "all"],
        "recur": lambda: NAMED_PERIODS,
    }
    if attr in _DATE_ATTRS:
        return DATE_KEYWORDS
    return values[attr]() if attr in values else ()


def complete(argv: Sequence[str], db_path: Path) -> str:
    """Return the output of ``tk _complete ARGV``: one candidate per line.

    ``argv[0]`` is the current word prefixed with ``_``; the rest are the words before it.
    """
    if not argv or not argv[0].startswith("_"):
        return ""
    found = candidates(argv[1:], argv[0][1:], Data(db_path))
    return "".join(f"{option}\n" for option in found)


def script(shell: str, names: Sequence[str]) -> str:
    """Return the completion script for ``shell``, registering it for ``names``.

    Raises:
        UsageError: If ``shell`` is not one of :data:`SHELLS`.
    """
    if shell == "powershell":
        return _POWERSHELL.replace("{names}", ", ".join(names))
    if shell == "bash":
        return _BASH.replace("{names}", " ".join(names))
    raise UsageError("error.completion_shell", shell=shell, shells=", ".join(SHELLS))


_POWERSHELL = """\
# TAME completion for PowerShell (tk completion powershell). Remove this block to undo.
Register-ArgumentCompleter -Native -CommandName {names} -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    $limit = $cursorPosition - $wordToComplete.Length
    $before = @(
        $commandAst.CommandElements | Select-Object -Skip 1 |
            Where-Object { $_.Extent.EndOffset -le $limit } |
            ForEach-Object { $_.Extent.Text }
    )
    $exe = $commandAst.CommandElements[0].Extent.Text
    # tk prints UTF-8; PowerShell would decode it with the console code page (850, 437...).
    $encoding = [Console]::OutputEncoding
    try {
        [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
        $found = @(& $exe _complete "_$wordToComplete" @before 2>$null)
    } finally {
        [Console]::OutputEncoding = $encoding
    }
    $found | ForEach-Object {
        [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
    }
}
"""

_BASH = """\
# TAME completion for bash (tk completion bash). Remove this block to undo.
_tame_complete() {
    local line="${COMP_LINE:0:COMP_POINT}" cur=""
    local -a words
    read -ra words <<< "$line"
    if [[ "$line" != *[[:space:]] ]]; then
        cur="${words[${#words[@]}-1]}"
        unset 'words[${#words[@]}-1]'
    fi
    local IFS=$'\\n'
    local -a found
    found=($("${words[0]}" _complete "_$cur" "${words[@]:1}" 2>/dev/null))
    if [[ "$cur" == *:* ]]; then
        local head="${cur%"${cur##*:}"}"
        found=("${found[@]#"$head"}")
    fi
    COMPREPLY=("${found[@]}")
}
complete -o default -F _tame_complete {names}
"""
