"""Entry point for the ``tame`` and ``tk`` commands: parse, dispatch, exit code."""

import contextlib
import io
import sys
from collections.abc import Sequence

from tame.config import configured_language
from tame.errors import ExitCode, TameError
from tame.i18n import set_language, t


def _use_utf8_output() -> None:
    """Write UTF-8 even when redirected on Windows, where the default is the ANSI code page."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and stream.encoding.lower() != "utf-8":
            stream.reconfigure(encoding="utf-8")


def error_message(err: TameError) -> str:
    """Translate ``err``; parameters that are errors themselves are translated too."""
    params = {
        name: error_message(value) if isinstance(value, TameError) else value
        for name, value in err.params.items()
    }
    return t(err.key, **params)


def _complete(args: Sequence[str]) -> int:
    """Print completion candidates; never fails (a broken completion must stay silent)."""
    from tame.cli.completion import complete
    from tame.config import data_dir
    from tame.storage.repo import DB_FILENAME

    with contextlib.suppress(Exception):  # Completion must never print an error.
        if isinstance(sys.stdout, io.TextIOWrapper):  # LF only: bash keeps a CR on Windows.
            sys.stdout.reconfigure(newline="\n")
        sys.stdout.write(complete(args, data_dir() / DB_FILENAME))
    return ExitCode.OK


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Command-line arguments without the program name. Defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code (SPEC §5). Error messages go to stderr.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    _use_utf8_output()
    if args[:1] == ["_complete"]:  # Fast path for shell completion (SPEC §5).
        return _complete(args[1:])
    set_language(configured_language())
    from tame.cli import commands, eggs  # Imported here, after the completion fast path.
    from tame.cli.parser import parse_command

    try:
        if eggs.hatch(args):
            return ExitCode.OK
        return commands.run(parse_command(args))
    except TameError as err:
        print(error_message(err), file=sys.stderr)
        return err.exit_code
    except Exception as err:
        print(t("error.internal", detail=repr(err)), file=sys.stderr)
        return ExitCode.INTERNAL


if __name__ == "__main__":
    sys.exit(main())
