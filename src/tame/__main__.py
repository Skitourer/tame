"""Entry point for the ``tame`` and ``tk`` commands.

Minimal dispatcher for roadmap step 1: only ``version`` is wired. The hybrid
parser (SPEC §4) replaces this dispatch in step 3.
"""

import sys
from collections.abc import Sequence

from tame import __version__

EXIT_OK = 0
EXIT_USAGE = 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Command-line arguments without the program name. Defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code (SPEC §5: 0 ok, 1 usage error).
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["version"]:
        print(f"tame {__version__}")
        return EXIT_OK
    # TODO(step 7): route through t() once i18n lands.
    print(f"tame: unknown command: {' '.join(args) or '(none)'}", file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
