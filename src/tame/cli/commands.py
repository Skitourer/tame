"""Command handlers: one function per command, each returning an exit code."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from tame import __version__
from tame.cli.parser import ParsedCommand, parse_add, parse_filter
from tame.config import data_dir
from tame.core.service import TaskService, utc_now
from tame.errors import ExitCode, NoMatchError, UsageError
from tame.i18n import t
from tame.storage.migrations import SCHEMA_VERSION
from tame.storage.repo import DB_FILENAME, TaskRepo


@contextmanager
def open_service() -> Iterator[TaskService]:
    """Open the task database in the data directory and yield a service on it."""
    with TaskRepo(data_dir() / DB_FILENAME) as repo:
        yield TaskService(repo)


def _no_args(args: tuple[str, ...]) -> None:
    if args:
        raise UsageError("error.unexpected_argument", arg=args[0])


def cmd_add(command: ParsedCommand) -> int:
    """``add``: create a task and print its short id."""
    parsed = parse_add(command.args)
    with open_service() as service:
        task = service.add(
            parsed.description, project=parsed.project, tags=parsed.tags, priority=parsed.priority
        )
    print(t("cmd.add.created", id=task.id))
    return ExitCode.OK


def cmd_list(command: ParsedCommand) -> int:
    """``list``: print the matching tasks as a table."""
    where = parse_filter(command.filter)
    with open_service() as service:
        tasks = service.query(where)
    if not tasks:
        raise NoMatchError("error.no_matches")
    from tame.cli.render import print_task_table

    print_task_table(tasks, utc_now())
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
    "list": cmd_list,
    "version": cmd_version,
}


def run(command: ParsedCommand) -> int:
    """Run ``command`` and return its exit code."""
    return HANDLERS.get(command.name, cmd_not_implemented)(command)
