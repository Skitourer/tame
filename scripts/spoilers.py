"""Print the easter eggs, decoded from their tests. Spoilers ahead!

Usage: uv run python scripts/spoilers.py

The tests keep every trigger and reply in ROT13 (see SPEC §5). This script reads
tests/cli/test_eggs.py and prints, for each test, the command lines it runs and the
texts it expects, so the repository itself never holds them in clear.
"""

import ast
import codecs
from pathlib import Path

TESTS = Path(__file__).resolve().parent.parent / "tests" / "cli" / "test_eggs.py"


def _decoded(node: ast.Call, name: str, index: int) -> str | None:
    """Return the decoded string argument ``index`` of a call to ``name``, if any."""
    if not (isinstance(node.func, ast.Name) and node.func.id == name):
        return None
    if len(node.args) <= index:
        return None
    arg = node.args[index]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return codecs.decode(arg.value, "rot13")
    return None


def main() -> None:
    """Print each egg test's new triggers and replies, decoded."""
    seen: set[str] = set()
    tree = ast.parse(TESTS.read_text(encoding="utf-8"))
    for func in tree.body:
        if not (isinstance(func, ast.FunctionDef) and func.name.startswith("test_")):
            continue
        calls = sorted(
            (node for node in ast.walk(func) if isinstance(node, ast.Call)),
            key=lambda node: (node.lineno, node.col_offset),
        )
        triggers = [text for node in calls if (text := _decoded(node, "run", 1))]
        replies = [text for node in calls if (text := _decoded(node, "r", 0))]
        replies = [text for text in dict.fromkeys(replies) if text not in seen]
        if not replies:
            continue
        seen.update(replies)
        print(f"{func.name}:")
        for text in triggers:
            print(f"  tk {text}")
        for text in replies:
            print(f"    -> {text}")


if __name__ == "__main__":
    main()
