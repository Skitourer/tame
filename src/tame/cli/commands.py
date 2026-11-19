"""Command handlers: one function per command, each returning an exit code."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from tame import __version__
from tame.cli.parser import ParsedCommand, parse_add
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


def cmd_add(args: tuple[str, ...]) -> int:
    """``add``: create a task and print its short id."""
    parsed = parse_add(args)
    with open_service() as service:
        task = service.add(
            parsed.description, project=parsed.project, tags=parsed.tags, priority=parsed.priority
        )
    print(t("cmd.add.created", id=task.id))
    return ExitCode.OK


def cmd_list(args: tuple[str, ...]) -> int:
    """``list``: print pending tasks as a table."""
    _no_args(args)
    with open_service() as service:
        tasks = service.query()
    if not tasks:
        raise NoMatchError("error.no_matches")
    from tame.cli.render import print_task_table

    print_task_table(tasks, utc_now())
    return ExitCode.OK


def cmd_version(args: tuple[str, ...]) -> int:
    """``version``: print the app and schema versions."""
    _no_args(args)
    print(t("cmd.version.output", version=__version__, schema=SCHEMA_VERSION))
    return ExitCode.OK


HANDLERS: dict[str, Callable[[tuple[str, ...]], int]] = {
    "add": cmd_add,
    "list": cmd_list,
    "version": cmd_version,
}


def run(command: ParsedCommand) -> int:
    """Run ``command`` and return its exit code."""
    return HANDLERS[command.name](command.args)
