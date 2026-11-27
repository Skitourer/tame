"""Command handlers: one function per command, each returning an exit code."""

import codecs
import io
import os
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from tame import __version__
from tame.cli import eggs, kindness, render
from tame.cli.parser import (
    ALL_FLAG,
    ParsedCommand,
    match_command,
    parse_add,
    parse_filter,
    parse_modify,
)
from tame.cli.render import task_ref
from tame.config import (
    OPTIONS,
    ConfigError,
    Option,
    Settings,
    config_path,
    data_dir,
    ensure_config_file,
    format_value,
    invalid_value,
    load_settings,
    option,
    parse_text,
    write_value,
)
from tame.core.dates import utc_now
from tame.core.filters import ALL, Filter
from tame.core.models import Status, Task
from tame.core.service import DoneResult, TaskService
from tame.core.urgency import by_urgency, urgency
from tame.errors import ExitCode, NoMatchError, UsageError, ValidationError
from tame.i18n import available_languages, t
from tame.io import tw_json
from tame.storage.migrations import SCHEMA_VERSION
from tame.storage.repo import DB_FILENAME, TaskRepo


@contextmanager
def open_service(settings: Settings) -> Iterator[TaskService]:
    """Open the task database in the data directory and yield a service on it."""
    with TaskRepo(data_dir() / DB_FILENAME) as repo:
        yield TaskService(repo, undo_retention=settings.undo_retention)


def _no_args(args: tuple[str, ...]) -> None:
    if args:
        raise UsageError("error.unexpected_argument", arg=args[0])


def _required_filter(command: ParsedCommand) -> Filter:
    """Parse the filter of a write command, which must not be empty (no accidental bulk)."""
    if not command.filter:
        raise UsageError("error.filter_required", command=command.name)
    return parse_filter(command.filter)


def _matching(service: TaskService, where: Filter) -> list[Task]:
    if not (tasks := service.query(where)):
        raise NoMatchError("error.no_matches")
    return tasks


def confirm(question: str) -> bool:
    """Ask a y/N question on stdout; anything but a yes word, or end of input, means no.

    Yes words come from ``confirm.yes`` (comma-separated); y and yes always work.
    """
    try:
        answer = render.ask(question)
    except EOFError:
        print()
        return False
    yes = {"y", "yes", *(word.strip().casefold() for word in t("confirm.yes").split(","))}
    return answer.strip().casefold() in yes


def _confirmed(
    command: ParsedCommand,
    tasks: Sequence[Task],
    one_key: str,
    many_key: str,
    threshold: int | None,
) -> bool:
    """Ask for confirmation unless ``--yes``; only above ``threshold`` unless it is None."""
    if command.yes or (threshold is not None and len(tasks) <= threshold):
        return True
    if len(tasks) == 1:
        question = t(one_key, task=task_ref(tasks[0]), description=tasks[0].description)
    else:
        question = t(many_key, count=len(tasks))
    if confirm(question):
        return True
    render.hint(t("confirm.cancelled"))
    return False


def _report(key: str, before: Sequence[Task], changed: Sequence[Task]) -> None:
    """Print ``key`` for each changed task, named as the user knew it before the command."""
    uuids = {task.uuid for task in changed}
    for task in before:
        if task.uuid in uuids:
            render.success(t(key, task=task_ref(task), description=task.description))


def cmd_add(command: ParsedCommand, settings: Settings) -> int:
    """``add``: create a task and print its short id."""
    parsed = parse_add(command.args)
    with open_service(settings) as service:
        task = service.add(
            parsed.description,
            project=parsed.project,
            tags=parsed.tags,
            priority=parsed.priority,
            due=parsed.due,
            wait=parsed.wait,
            depends=parsed.depends,
            recur=parsed.recur,
            until=parsed.until,
        )
    render.success(t("cmd.add.created", id=task.id))
    return ExitCode.OK


def cmd_list(command: ParsedCommand, settings: Settings) -> int:
    """``list``: print the matching tasks as a table, most urgent first.

    Without a filter and without any task at all, print a welcome message instead.
    """
    return _show_tasks(command, settings, limit=None)


def cmd_next(command: ParsedCommand, settings: Settings) -> int:
    """``next``: like ``list``, without blocked tasks, ``next_limit`` tasks, compact columns."""
    return _show_tasks(command, settings, limit=settings.next_limit)


def _show_tasks(command: ParsedCommand, settings: Settings, limit: int | None) -> int:
    """Print ``list`` (``limit`` None) or ``next`` (the ``limit`` first unblocked tasks)."""
    now = utc_now()
    where = parse_filter(command.filter, now)
    if limit is not None:
        where = replace(where, virtual_out=where.virtual_out | {"BLOCKED"})
    with open_service(settings) as service:
        found, hidden = service.query_hidden(where)
        links = service.links()
        if not found:
            if not command.filter and not service.query(Filter(status=ALL)):
                render.say(t("welcome").strip())  # First run: no task at all.
                return ExitCode.OK
            if hidden:
                render.say(_hidden_line(hidden), "summary")
            raise NoMatchError("error.no_matches")
    tasks = by_urgency(found, now, settings.urgency, links)
    shown = tasks[:limit]
    render.print_task_table(
        shown,
        now,
        coefficients=settings.urgency,
        date_format=settings.date_format,
        compact=limit is not None,
        links=links,
    )
    render.emit([[], render.summary_line(len(shown), tasks, now)])
    if len(shown) < len(tasks):
        render.say(t("next.more"), "summary")
    if hidden:
        render.say(_hidden_line(hidden), "summary")
    return ExitCode.OK


def _hidden_line(count: int) -> str:
    """Return the line telling how many waiting tasks a report left out."""
    return t("list.waiting_one") if count == 1 else t("list.waiting_many", count=count)


def cmd_done(command: ParsedCommand, settings: Settings) -> int:
    """``done``: mark the matching tasks completed."""
    where = _required_filter(command)
    with open_service(settings) as service:
        tasks = _matching(service, where)
        if not _confirmed(
            command,
            tasks,
            "confirm.done.one",
            "confirm.done.many",
            threshold=settings.confirm_threshold,
        ):
            return ExitCode.OK
        result = service.done(tasks)
        changed = result.done
        unblocked = service.unblocked_by(changed)
        word = None
        if changed and settings.kindness and kindness.is_terminal() and not service.query():
            word = kindness.draw(service, utc_now(), "empty")
    _report("cmd.done.task", tasks, changed)
    _report_series(result, settings)
    for task in unblocked:
        render.success(t("cmd.done.unblocked", task=task_ref(task), description=task.description))
    if word is not None:
        kindness.show(word)
    uuids = {task.uuid for task in changed}
    eggs.after_done([task for task in tasks if task.uuid in uuids])
    return ExitCode.OK


def _report_series(result: DoneResult, settings: Settings) -> None:
    """Tell what became of the recurring tasks just completed (SPEC §4 Recurrence)."""
    for _, new in result.next:
        due = new.due.astimezone().strftime(settings.date_format) if new.due else ""
        render.success(t("cmd.done.next", task=task_ref(new), description=new.description, due=due))
    for task in result.last:
        render.hint(t("cmd.done.last", task=task_ref(task), description=task.description))
    for task in result.unknown:
        render.warning(
            t(
                "cmd.done.unknown",
                task=task_ref(task),
                description=task.description,
                recur=task.recur,
            )
        )


def cmd_start(command: ParsedCommand, settings: Settings) -> int:
    """``start``: start work on the matching tasks (one active task unless ``multiple_active``)."""
    where = _required_filter(command)
    with open_service(settings) as service:
        tasks = _matching(service, where)
        if not _confirmed(
            command,
            tasks,
            "confirm.start.one",
            "confirm.start.many",
            threshold=settings.confirm_threshold,
        ):
            return ExitCode.OK
        result = service.start(tasks, multiple_active=settings.multiple_active)
    for task, session in result.stopped:
        _say_stopped(task, session.duration)
    _report("cmd.start.task", tasks, result.started)
    for task in result.already:
        render.hint(t("cmd.start.already", task=task_ref(task), description=task.description))
    return ExitCode.OK


def cmd_stop(command: ParsedCommand, settings: Settings) -> int:
    """``stop``: stop the active tasks (all of them, or those the filter picks)."""
    where = parse_filter(command.filter)
    where = replace(where, virtual_in=where.virtual_in | {"ACTIVE"})
    with open_service(settings) as service:
        stopped = service.stop(service.query(where, include_waiting=True))
    if not stopped:
        raise NoMatchError("error.no_active")
    for task, session in stopped:
        _say_stopped(task, session.duration)
    return ExitCode.OK


def _say_stopped(task: Task, spent: timedelta) -> None:
    render.success(
        t(
            "cmd.stop.task",
            task=task_ref(task),
            description=task.description,
            duration=render.format_duration(spent),
        )
    )


def cmd_delete(command: ParsedCommand, settings: Settings) -> int:
    """``delete``: soft-delete the matching tasks; always asks unless ``--yes``."""
    where = _required_filter(command)
    with open_service(settings) as service:
        tasks = _matching(service, where)
        if not _confirmed(
            command, tasks, "confirm.delete.one", "confirm.delete.many", threshold=None
        ):
            return ExitCode.OK
        changed = service.delete(tasks)
    _report("cmd.delete.task", tasks, changed)
    return ExitCode.OK


PURGE_WORD = "purge"
"""Word to type to confirm ``purge --all``, the same in every language."""


def cmd_purge(command: ParsedCommand, settings: Settings) -> int:
    """``purge``: remove deleted tasks for good, or every task with ``--all``.

    A backup of the database is written first; the undo history is cleared.
    """
    everything = command.args == (ALL_FLAG,)
    if everything and command.filter:
        raise UsageError("error.purge_all_filter")
    if everything and not keyboard_input():
        raise UsageError("error.purge_all_terminal")
    where = None if everything else _purge_filter(command.filter)
    with open_service(settings) as service:
        if where is None:
            count = len(service.query(Filter(status=ALL), include_waiting=True))
            if not count:
                raise NoMatchError("error.nothing_to_purge")
            if not _purge_all_confirmed(command, count):
                render.hint(t("confirm.cancelled"))
                return ExitCode.OK
            result = service.purge_all()
        else:
            tasks = service.query(where)
            if not tasks:
                raise NoMatchError("error.nothing_to_purge")
            if not _confirmed(
                command, tasks, "confirm.purge.one", "confirm.purge.many", threshold=None
            ):
                return ExitCode.OK
            result = service.purge(tasks)
    count = len(result.purged)
    key = "cmd.purge.done_one" if count == 1 else "cmd.purge.done_many"
    render.success(t(key, count=count))
    render.say(t("cmd.purge.backup", path=str(result.backup)))
    render.hint(t("cmd.purge.no_undo"))
    return ExitCode.OK


def keyboard_input() -> bool:
    """True if stdin is a keyboard: a terminal, and on Windows a real console.

    Windows reports ``NUL`` (``< NUL``, ``< /dev/null``) as a tty; only a console
    handle has a console mode.
    """
    if not render.is_terminal(sys.stdin):
        return False
    if sys.platform != "win32":
        return True
    import ctypes
    import msvcrt

    try:
        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
    except (OSError, ValueError, io.UnsupportedOperation):
        return True  # no OS handle (replaced stream): trust isatty()
    mode = ctypes.c_ulong()
    return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)))


def _purge_filter(tokens: tuple[str, ...]) -> Filter:
    """The filter of ``purge``: always on deleted tasks; another ``status:`` is an error."""
    where = parse_filter(tokens)
    if where.status not in (None, Status.DELETED):
        raise UsageError("error.purge_status")
    return replace(where, status=Status.DELETED)


def _purge_all_confirmed(command: ParsedCommand, count: int) -> bool:
    """y/N (``--yes`` skips it), then the word ``purge`` typed in full (never skipped)."""
    if not command.yes and not confirm(t("confirm.purge.all", count=count)):
        return False
    try:
        answer = render.ask(t("confirm.purge.word", word=PURGE_WORD), yes_no=False)
    except EOFError:
        print()
        return False
    return answer.strip() == PURGE_WORD


def cmd_modify(command: ParsedCommand, settings: Settings) -> int:
    """``modify``: apply the argument mods to the matching tasks."""
    where = _required_filter(command)
    if not (changes := parse_modify(command.args)):
        raise UsageError("error.no_modifications")
    with open_service(settings) as service:
        tasks = _matching(service, where)
        if not _confirmed(
            command,
            tasks,
            "confirm.modify.one",
            "confirm.modify.many",
            threshold=settings.confirm_threshold,
        ):
            return ExitCode.OK
        changed = service.modify(tasks, changes)
    if not changed:
        render.hint(t("cmd.modify.unchanged"))
    _report("cmd.modify.task", tasks, changed)
    return ExitCode.OK


def cmd_annotate(command: ParsedCommand, settings: Settings) -> int:
    """``annotate``: add the argument text as an annotation to the matching tasks."""
    where = _required_filter(command)
    if not (text := _text(command.args)):
        raise UsageError("error.empty_annotation")
    with open_service(settings) as service:
        tasks = _matching(service, where)
        if not _confirmed(
            command,
            tasks,
            "confirm.annotate.one",
            "confirm.annotate.many",
            threshold=settings.confirm_threshold,
        ):
            return ExitCode.OK
        changed = service.annotate(tasks, text)
    _report("cmd.annotate.task", tasks, changed)
    return ExitCode.OK


def cmd_denotate(command: ParsedCommand, settings: Settings) -> int:
    """``denotate``: remove one annotation (matching the argument text) from the tasks."""
    where = _required_filter(command)
    text = _text(command.args)
    with open_service(settings) as service:
        tasks = _matching(service, where)
        if not _confirmed(
            command,
            tasks,
            "confirm.denotate.one",
            "confirm.denotate.many",
            threshold=settings.confirm_threshold,
        ):
            return ExitCode.OK
        if not (changed := service.denotate(tasks, text)):
            raise NoMatchError("error.no_annotation" if text else "error.no_notes", text=text)
    _report("cmd.denotate.task", tasks, changed)
    return ExitCode.OK


def _text(args: Sequence[str]) -> str:
    """Join free-text arguments; the first ``--`` (rule 5) is dropped."""
    words = list(args)
    if "--" in words:
        words.remove("--")
    return " ".join(words).strip()


def cmd_info(command: ParsedCommand, settings: Settings) -> int:
    """``info``: print every field of the matching tasks."""
    where = parse_filter(command.filter)
    with open_service(settings) as service:
        tasks = _matching(service, where)
        tagger = service.virtual_tagger()
        virtual = {task.uuid: tagger(task) for task in tasks}
        links = service.links()
        related = {
            task.uuid: render.Related(
                depends=sorted(
                    (service.get(uuid) or uuid for uuid in task.depends), key=_dependency_order
                ),
                blocking=service.dependents(task),
                links=links,
            )
            for task in tasks
        }
    render.print_task_info(
        tasks,
        utc_now(),
        virtual=virtual,
        coefficients=settings.urgency,
        date_format=settings.date_format,
        related=related,
    )
    return ExitCode.OK


def _dependency_order(task: Task | str) -> tuple[int, int, str]:
    """Pending tasks by id first, then the others by uuid, then missing ones."""
    if isinstance(task, str):
        return 2, 0, task
    if task.id is not None:
        return 0, task.id, task.uuid
    return 1, 0, task.uuid


def cmd_undo(command: ParsedCommand, settings: Settings) -> int:
    """``undo``: revert the last write command."""
    _no_args(command.args)
    with open_service(settings) as service:
        try:
            result = service.undo()
        except NoMatchError as err:
            render.error(t(err.key, **err.params))
            eggs.after_empty_undo()
            return err.exit_code
    render.success(t("cmd.undo.header", command=result.cmd))
    for task in result.restored:
        render.success(t("cmd.undo.restored", task=task_ref(task), description=task.description))
    for task in result.removed:
        render.success(t("cmd.undo.removed", task=task_ref(task), description=task.description))
    return ExitCode.OK


def cmd_completion(command: ParsedCommand, settings: Settings) -> int:
    """``completion``: print the Tab completion script for a shell."""
    from tame import alias
    from tame.cli import completion

    match command.args:
        case (shell,):
            names = ["tk", "tame", *alias.installed()]
            print(completion.script(shell, names), end="")
        case _:  # No shell, or too many words: say what to type.
            raise UsageError("error.completion_usage", shells=" | ".join(completion.SHELLS))
    return ExitCode.OK


def cmd_version(command: ParsedCommand, settings: Settings) -> int:
    """``version``: print the app and schema versions."""
    _no_args(command.args)
    render.say(t("cmd.version.output", version=__version__, schema=SCHEMA_VERSION))
    render.say(t("cmd.version.more"), "hint")
    return ExitCode.OK


def cmd_print(command: ParsedCommand, settings: Settings) -> int:
    """``print``: a printable page of the matching tasks, opened in the browser.

    With ``--file PATH``, the page is saved there instead, without opening it.
    """
    now = utc_now()
    where = parse_filter(command.filter, now)
    target = command.args[1] if command.args else None
    with open_service(settings) as service:
        tasks = _matching(service, where)
        links = service.links()
        word = kindness.draw(service, now) if target is None and settings.kindness else None
    from tame.cli.printout import print_page

    page = print_page(
        tasks,
        now,
        filter_text=" ".join(command.filter),
        coefficients=settings.urgency,
        date_format=settings.date_format,
        auto_print=target is None,
        kind_word=None if word is None else f"{kindness.HEART} {word}",
        links=links,
    )
    if target is None:
        path = Path(tempfile.gettempdir()) / f"tame-print-{now:%Y%m%d-%H%M%S}.html"
    else:
        path = Path(target)
    try:
        path.write_text(page, encoding="utf-8")
    except OSError as exc:
        raise UsageError("error.print_io", path=str(path), detail=exc.strerror) from exc
    if target is not None:
        render.success(t("cmd.print.saved", path=path))
    elif _open_in_browser(path):
        render.success(t("cmd.print.opened", path=path))
    else:
        render.say(t("cmd.print.not_opened", path=path))
    return ExitCode.OK


def _open_in_browser(path: Path) -> bool:
    """Open ``path`` in the default browser; return False if none could be started."""
    import webbrowser

    return webbrowser.open(path.resolve().as_uri())


def cmd_export(command: ParsedCommand, settings: Settings) -> int:
    """``export``: print the matching tasks as Taskwarrior JSON (``[]`` if none)."""
    now = utc_now()
    where = parse_filter(command.filter, now)
    with open_service(settings) as service:
        tasks = service.query(where, include_waiting=True)
        links = service.links()
    print(
        tw_json.dumps(
            tw_json.task_to_tw(task, urgency(task, now, settings.urgency, links)) for task in tasks
        )
    )
    return ExitCode.OK


def cmd_import(command: ParsedCommand, settings: Settings) -> int:
    """``import``: merge Taskwarrior JSON from a file, or stdin if none or ``-``."""
    match command.args:
        case () | ("-",):
            text = _decode(sys.stdin.buffer.read())
        case (path,):
            try:
                text = _decode(Path(path).read_bytes())
            except OSError as exc:
                raise UsageError("error.import_io", path=path, detail=exc.strerror) from exc
        case _:
            raise UsageError("error.unexpected_argument", arg=command.args[1])
    now = utc_now()
    tasks = []
    for number, item in enumerate(tw_json.loads(text), start=1):
        try:
            tasks.append(tw_json.task_from_tw(item, now))
        except ValidationError as err:
            raise ValidationError("error.import_item", item=number, detail=err) from err
    with open_service(settings) as service:
        stored = service.query(include_waiting=True)
        tasks, converted = tw_json.convert_recurring(tasks, stored, now)
        result = service.import_tasks(tasks)
    render.success(
        t(
            "cmd.import.summary",
            added=len(result.added),
            updated=len(result.updated),
            skipped=len(result.skipped),
        )
    )
    if converted:
        render.say(t("cmd.import.converted", count=converted))
    return ExitCode.OK


def _decode(data: bytes) -> str:
    """Decode UTF-8, or UTF-16 with a byte order mark (PowerShell 5 ``>`` writes it)."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("error.import_json", detail=str(exc)) from None


def cmd_alias(command: ParsedCommand, settings: Settings) -> int:
    """``alias``: create or remove an opt-in command alias such as ``task``."""
    from tame import alias

    match command.args:
        case ("install", name):
            result = alias.install(name)
            render.success(t("cmd.alias.installed", name=name, path=result.path))
            if not result.on_path:
                render.warning(t("cmd.alias.not_on_path", name=name, dir=result.path.parent))
            elif result.shadowed_by is not None:
                render.warning(t("cmd.alias.shadowed", name=name, path=result.shadowed_by))
        case ("remove", name):
            render.success(t("cmd.alias.removed", name=name, path=alias.remove(name)))
        case _:
            raise UsageError("error.alias_usage")
    return ExitCode.OK


def cmd_config(command: ParsedCommand) -> int:
    """``config``: show or change settings in ``config.toml``.

    ``tk config`` lists all settings; then ``get KEY``, ``set KEY VALUE``,
    ``unset KEY`` (back to the default), ``path`` and ``edit``.
    """
    match command.args:
        case ():
            values = load_settings().values
            for opt in OPTIONS:
                line = f"{opt.key} = {format_value(values[opt.key])}"
                if values[opt.key] != opt.default:
                    line += "  " + t("cmd.config.default", value=format_value(opt.default))
                render.say(line)
        case ("get", key):
            value = load_settings().values[option(key).key]
            print(value if isinstance(value, str) else format_value(value))
        case ("set", key, text):
            opt = option(key)
            try:
                value = parse_text(opt, text)
            except ValueError:
                raise invalid_value(opt, text) from None
            write_value(opt.key, value)
            render.success(t("cmd.config.set", name=opt.key, value=format_value(value)))
        case ("unset", key):
            opt = option(key)
            write_value(opt.key, opt.default)
            render.success(t("cmd.config.unset", name=opt.key, value=format_value(opt.default)))
        case ("path",):
            print(config_path())
        case ("edit",):
            _edit_file(ensure_config_file())
            load_settings()  # Report mistakes right away.
        case _:
            raise ConfigError("error.config_usage")
    return ExitCode.OK


def _edit_file(path: Path) -> None:
    """Open ``path`` in ``$VISUAL``/``$EDITOR``, else Notepad (Windows) or vi, and wait."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    editor = editor or ("notepad" if sys.platform == "win32" else "vi")
    argv = [*shlex.split(editor, posix=sys.platform != "win32"), str(path)]
    try:
        subprocess.run(argv, check=False)
    except OSError as exc:
        raise UsageError("error.editor_failed", editor=editor, detail=str(exc)) from exc


HELP_COMMANDS = (
    "add",
    "list",
    "next",
    "info",
    "modify",
    "annotate",
    "denotate",
    "start",
    "stop",
    "done",
    "delete",
    "undo",
    "purge",
    "print",
    "export",
    "import",
    "config",
    "alias",
    "help",
    "version",
)
"""Commands shown by ``tk help``, in this order: the implemented ones."""

HELP_TOPICS = ("filters", "dates", "urgency", "security", "settings", "tour", "license", "credits")
"""Help topics that are not commands."""


def cmd_help(command: ParsedCommand) -> int:
    """``help``: list commands, or show the help of a command or topic."""
    match command.args:
        case ():
            render.print_help(help_overview(), commands=HELP_COMMANDS)
        case ("config", key):
            render.print_help(settings_help(key))
        case (subject,):
            render.print_help(help_text(subject))
        case _:
            raise UsageError("error.unexpected_argument", arg=command.args[1])
    return ExitCode.OK


def help_overview() -> str:
    """Return the ``tk help`` text: usage, commands with summaries, topics."""
    width = max(len(name) for name in HELP_COMMANDS)
    lines = [t("help.usage"), "", t("help.commands")]
    lines += [f"  {name:<{width}}  {t(f'help.cmd.{name}.summary')}" for name in HELP_COMMANDS]
    lines += ["", t("help.topics", topics=" | ".join(HELP_TOPICS)), t("help.more")]
    return "\n".join(lines)


def license_help() -> str:
    """Return ``tk help license``: TAME's license, then the installed libraries' licenses."""
    from tame import about

    text = about.license_text()
    parts = [t("about.license_header"), text.strip() if text else t("about.license_missing")]
    libraries = about.libraries()
    if libraries:
        name_width = max(len(library.name) for library in libraries)
        version_width = max(len(library.version) for library in libraries)
        rows = [
            f"  {lib.name:<{name_width}}  {lib.version:<{version_width}}  {lib.license}"
            for lib in libraries
        ]
        parts.append(t("about.libraries") + "\n" + "\n".join(rows))
    return "\n\n".join(parts)


def settings_help(key: str | None = None) -> str:
    """Return ``tk help settings`` (every setting), or ``tk help config KEY`` (one).

    Each setting shows what it does, its possible values and its default; one setting
    also shows its current value, if ``config.toml`` can be read.

    Raises:
        ConfigError: If ``key`` names no setting.
    """
    languages = ", ".join(available_languages())

    def describe(opt: Option) -> list[str]:
        values = t(
            "help.settings.values",
            values=t(opt.expected, languages=languages),
            default=format_value(opt.default),
        )
        return [t(f"setting.help.{opt.key}"), values]

    if key is None:
        lines = [t("help.settings.intro")]
        for opt in OPTIONS:
            lines += ["", f"  {opt.key}", *(f"      {line}" for line in describe(opt))]
        return "\n".join([*lines, "", t("help.settings.more")])
    opt = option(key)
    lines = [t("help.usage_label", usage=f"tk config set {opt.key} VALUE"), "", *describe(opt)]
    try:
        current = load_settings().values[opt.key]
    except ConfigError:
        pass
    else:
        lines.append(t("help.settings.current", value=format_value(current)))
    return "\n".join(lines)


def help_text(subject: str) -> str:
    """Return the help of a topic, or of a command (exact name or unique prefix).

    Raises:
        UsageError: If ``subject`` is ambiguous or names nothing documented.
    """
    if subject == "license":
        return license_help()
    if subject == "settings":
        return settings_help()
    if subject in HELP_TOPICS:
        return t(f"help.topic.{subject}").rstrip()
    name = match_command(subject)
    if name not in (*HELP_COMMANDS, "completion"):  # completion: advanced, not listed
        raise UsageError("error.help_unknown", name=subject)
    usage = t("help.usage_label", usage=t(f"help.cmd.{name}.usage"))
    summary = t(f"help.cmd.{name}.summary")
    return f"{usage}\n\n{summary}.\n\n{t(f'help.cmd.{name}.body').rstrip()}"


def _touches_completion(args: Sequence[str]) -> bool:
    """True if a ``config`` command may have changed the ``completion`` setting."""
    return tuple(args[:2]) in (("set", "completion"), ("unset", "completion")) or tuple(
        args[:1]
    ) == ("edit",)


def _sync_completion(settings: Settings, *, explicit: bool = False) -> None:
    """Align the shell profiles with the ``completion`` setting, in a terminal only."""
    from tame import alias
    from tame.cli import shellprofile

    if not shellprofile.is_terminal():
        return
    names = ["tk", "tame", *alias.installed()]
    try:
        with open_service(settings) as service:
            messages = shellprofile.reconcile(
                service, settings.completion, names, explicit=explicit
            )
    except OSError as exc:
        if explicit:
            render.warning(t("completion.error", detail=str(exc)))
        return
    for message in messages:
        render.say(message)


HANDLERS: dict[str, Callable[[ParsedCommand, Settings], int]] = {
    "add": cmd_add,
    "alias": cmd_alias,
    "annotate": cmd_annotate,
    "completion": cmd_completion,
    "delete": cmd_delete,
    "denotate": cmd_denotate,
    "done": cmd_done,
    "export": cmd_export,
    "import": cmd_import,
    "info": cmd_info,
    "list": cmd_list,
    "modify": cmd_modify,
    "next": cmd_next,
    "print": cmd_print,
    "purge": cmd_purge,
    "start": cmd_start,
    "stop": cmd_stop,
    "undo": cmd_undo,
    "version": cmd_version,
}


def run(command: ParsedCommand) -> int:
    """Run ``command`` with the settings from ``config.toml`` and return its exit code.

    ``config`` and ``help`` run without loading them: they must work, and help repair,
    when the file is invalid.
    """
    if command.name == "config":
        code = cmd_config(command)
        if code == ExitCode.OK and _touches_completion(command.args):
            _sync_completion(load_settings(), explicit=True)
        return code
    if command.name == "help":
        return cmd_help(command)
    settings = load_settings()
    if command.implicit:
        command = replace(command, name=settings.default_command)
    code = HANDLERS[command.name](command, settings)
    if code == ExitCode.OK:
        _sync_completion(settings)
    if (
        code == ExitCode.OK
        and command.name in kindness.ELIGIBLE
        and settings.kindness
        and kindness.is_terminal()
    ):
        now = utc_now()
        with open_service(settings) as service:
            word = kindness.draw(service, now) if kindness.is_due(service, now) else None
        if word is not None:
            kindness.show(word)
    return code
