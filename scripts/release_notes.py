"""Print the GitHub release notes for a version: how to install, then its CHANGELOG section.

Usage: python scripts/release_notes.py 0.1.0

Exits non-zero if CHANGELOG.md has no ``## [0.1.0]`` section, so a release cannot go out
without its notes.
"""

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"

INSTALL = """\
## Install

**Windows**: open PowerShell, paste this line, press Enter (no Python needed):

```powershell
irm https://skitourer.github.io/tame/install.ps1 | iex
```

**Linux**: `curl -LsSf https://skitourer.github.io/tame/install.sh | sh`

**With uv**: `uv tool install tame-tasks` | **Update**: run the same line again, or
`uv tool upgrade tame-tasks`.

Step by step: [Installation for beginners](https://skitourer.github.io/tame/install-beginners/)

Documentation: https://skitourer.github.io/tame/
"""


def section(version: str, changelog: str) -> str:
    """Return the body of the ``## [version]`` section of ``changelog``.

    Raises:
        ValueError: If there is no such section.
    """
    match = re.search(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", changelog, re.M | re.S
    )
    if match is None:
        raise ValueError(f"CHANGELOG.md has no section for {version}")
    return match[1].strip()


def main() -> None:
    """Print the notes for the version given as first argument."""
    version = sys.argv[1].removeprefix("v")
    try:
        changes = section(version, CHANGELOG.read_text(encoding="utf-8"))
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{INSTALL}\n## What's new\n\n{changes}")


if __name__ == "__main__":
    main()
