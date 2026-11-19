"""Command handlers: one function per command, each returning an exit code."""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager

from tame import __version__
from tame.cli.parser import ParsedCommand, parse_add, parse_filter, parse_modify
from tame.config import data_dir
from tame.core.dates import utc_now
from tame.core.filters import Filter
from tame.core.models import Task
from tame.core.service import TaskService
from tame.core.urgency import by_urgency
from tame.errors import ExitCode, NoMatchError, UsageError
from tame.i18n import t
from tame.storage.migrations import SCHEMA_VERSION
from tame.storage.repo import DB_FILENAME, TaskRepo


@contextmanager
def open_service() -> Iterator[TaskService]:
    """Open the task database in the data directory and yield a service on it."""
    with TaskRepo(data_dir() / DB_FILENAME) as repo:
        yield TaskService(repo)


CONFIRM_THRESHOLD = 3
"""Write commands on more tasks than this ask for confirmation (configurable in step 7)."""

_YES_ANSWERS = frozenset({"y", "yes"})


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


def task_ref(task: Task) -> str:
    """Return how a task is named in messages: its short id, else its uuid's first 8 chars."""
    return str(task.id) if task.id is not None else task.uuid[:8]


def confirm(question: str) -> bool:
    """Ask a y/N question on stdout; anything but y/yes, or end of input, means no."""
    try:
        answer = input(f"{question} {t('confirm.choices')} ")
    except EOFError:
        print()
        return False
    return answer.strip().casefold() in _YES_ANSWERS


def _confirmed(
    command: ParsedCommand, tasks: Sequence[Task], one_key: str, many_key: str, always: bool
) -> bool:
    """Ask for confirmation unless ``--yes``; only above the threshold unless ``always``."""
    if command.yes or (not always and len(tasks) <= CONFIRM_THRESHOLD):
        return True
    if len(tasks) == 1:
        question = t(one_key, task=task_ref(tasks[0]), description=tasks[0].description)
    else:
        question = t(many_key, count=len(tasks))
    if confirm(question):
        return True
    print(t("confirm.cancelled"))
    return False


def _report(key: str, before: Sequence[Task], changed: Sequence[Task]) -> None:
    """Print ``key`` for each changed task, named as the user knew it before the command."""
    uuids = {task.uuid for task in changed}
    for task in before:
        if task.uuid in uuids:
            print(t(key, task=task_ref(task), description=task.description))


def cmd_add(command: ParsedCommand) -> int:
    """``add``: create a task and print its short id."""
    parsed = parse_add(command.args)
    with open_service() as service:
        task = service.add(
            parsed.description,
            project=parsed.project,
            tags=parsed.tags,
            priority=parsed.priority,
            due=parsed.due,
        )
    print(t("cmd.add.created", id=task.id))
    return ExitCode.OK


def cmd_list(command: ParsedCommand) -> int:
    """``list``: print the matching tasks as a table, most urgent first."""
    now = utc_now()
    where = parse_filter(command.filter, now)
    with open_service() as service:
        tasks = by_urgency(_matching(service, where), now)
    from tame.cli.render import print_task_table

    print_task_table(tasks, now)
    return ExitCode.OK


def cmd_done(command: ParsedCommand) -> int:
    """``done``: mark the matching tasks completed."""
    where = _required_filter(command)
    with open_service() as service:
        tasks = _matching(service, where)
        if not _confirmed(command, tasks, "confirm.done.one", "confirm.done.many", always=False):
            return ExitCode.OK
        changed = service.complete(tasks)
    _report("cmd.done.task", tasks, changed)
    return ExitCode.OK


def cmd_delete(command: ParsedCommand) -> int:
    """``delete``: soft-delete the matching tasks; always asks unless ``--yes``."""
    where = _required_filter(command)
    with open_service() as service:
        tasks = _matching(service, where)
        if not _confirmed(command, tasks, "confirm.delete.one", "confirm.delete.many", always=True):
            return ExitCode.OK
        changed = service.delete(tasks)
    _report("cmd.delete.task", tasks, changed)
    return ExitCode.OK


def cmd_modify(command: ParsedCommand) -> int:
    """``modify``: apply the argument mods to the matching tasks."""
    where = _required_filter(command)
    if not (changes := parse_modify(command.args)):
        raise UsageError("error.no_modifications")
    with open_service() as service:
        tasks = _matching(service, where)
        if not _confirmed(
            command, tasks, "confirm.modify.one", "confirm.modify.many", always=False
        ):
            return ExitCode.OK
        changed = service.modify(tasks, changes)
    if not changed:
        print(t("cmd.modify.unchanged"))
    _report("cmd.modify.task", tasks, changed)
    return ExitCode.OK


def cmd_info(command: ParsedCommand) -> int:
    """``info``: print every field of the matching tasks."""
    where = parse_filter(command.filter)
    with open_service() as service:
        tasks = _matching(service, where)
    from tame.cli.render import print_task_info

    print_task_info(tasks, utc_now())
    return ExitCode.OK


def cmd_undo(command: ParsedCommand) -> int:
    """``undo``: revert the last write command."""
    _no_args(command.args)
    with open_service() as service:
        result = service.undo()
    print(t("cmd.undo.header", command=result.cmd))
    for task in result.restored:
        print(t("cmd.undo.restored", task=task_ref(task), description=task.description))
    for task in result.removed:
        print(t("cmd.undo.removed", task=task_ref(task), description=task.description))
    return ExitCode.OK


def cmd_version(command: ParsedCommand) -> int:
    """``version``: print the app and schema versions."""
    _no_args(command.args)
    print(t("cmd.version.output", version=__version__, schema=SCHEMA_VERSION))
    return ExitCode.OK


def cmd_not_implemented(command: ParsedCommand) -> int:
    """Placeholder for V1 commands of later roadmap steps."""
    raise UsageError("error.not_implemented", command=command.name)


HANDLERS: dict[str, Callable[[ParsedCommand], int]] = {
    "add": cmd_add,
    "delete": cmd_delete,
    "done": cmd_done,
    "info": cmd_info,
    "list": cmd_list,
    "modify": cmd_modify,
    "undo": cmd_undo,
    "version": cmd_version,
}


def run(command: ParsedCommand) -> int:
    """Run ``command`` and return its exit code."""
    return HANDLERS.get(command.name, cmd_not_implemented)(command)
