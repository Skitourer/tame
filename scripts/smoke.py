"""Smoke-test an installed tame: run the everyday commands and check their output.

Usage: python scripts/smoke.py BIN_DIR

BIN_DIR holds the installed ``tk`` command (for instance the ``UV_TOOL_BIN_DIR`` given to
``uv tool install``). Data goes to a temporary ``TAME_HOME``; the ``task`` alias is created
in BIN_DIR and removed at the end. Exits non-zero at the first failure.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

WINDOWS = sys.platform == "win32"


def main() -> None:
    """Run the scenario against the ``tk`` found in ``sys.argv[1]``."""
    bin_dir = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory() as home:
        env = {
            **os.environ,
            "TAME_HOME": home,
            "UV_TOOL_BIN_DIR": str(bin_dir),
            "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
        }

        def tk(*args: str, code: int = 0, program: str = "tk") -> str:
            argv = [program, *args]
            if WINDOWS and program == "task":
                argv = ["cmd", "/c", str(bin_dir / "task.cmd"), *args]
            else:
                argv[0] = str(bin_dir / program)
            done = subprocess.run(argv, env=env, capture_output=True, text=True, encoding="utf-8")
            line = " ".join([program, *args])
            print(f"$ {line}  -> {done.returncode}")
            if done.returncode != code:
                sys.exit(f"FAILED: expected exit {code}\n{done.stdout}{done.stderr}")
            return done.stdout

        def expect(text: str, output: str) -> None:
            if text not in output:
                sys.exit(f"FAILED: {text!r} not in output:\n{output}")

        expect("tame ", tk("version"))
        expect("Welcome to TAME!", tk())
        expect("Created task 1.", tk("add", "Call", "the", "bank", "+phone", "due:fri", "pri:H"))
        tk("add", "Water", "plants", "project:home")
        expect("Water plants", tk("list"))
        expect("Completed task 1", tk("1", "done"))
        expect("Undid 'done'.", tk("undo"))
        tk("+nothing", code=2)
        expect("A two-minute tour.", tk("help", "tour"))
        tk("config", "set", "language", "fr")
        expect("Usage : tk", tk("help"))
        tk("config", "set", "language", "en")
        backup = Path(home) / "backup.json"
        exported = tk("status:all", "export")
        if len(json.loads(exported)) != 2:
            sys.exit(f"FAILED: export\n{exported}")
        backup.write_text(exported, encoding="utf-8")
        (Path(home) / "tasks.db").unlink()
        expect("2 added", tk("import", str(backup)))
        expect("Created alias 'task'", tk("alias", "install", "task"))
        expect("Call the bank", tk("list", program="task"))
        expect("Removed alias 'task'", tk("alias", "remove", "task"))
        expect("tame ", tk("version", program="tame"))
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
