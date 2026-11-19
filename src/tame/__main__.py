"""Entry point for the ``tame`` and ``tk`` commands: parse, dispatch, exit code."""

import io
import sys
from collections.abc import Sequence

from tame.cli import commands, eggs
from tame.cli.parser import parse_command
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


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Command-line arguments without the program name. Defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code (SPEC §5). Error messages go to stderr.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    _use_utf8_output()
    set_language(configured_language())
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
