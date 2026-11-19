import re
from pathlib import Path

import tame
from tame.i18n import lookup, t

SRC = Path(tame.__file__).parent
# t("key"...) calls and TameError subclasses built with a literal key.
KEY_RE = re.compile(r"""(?:\bt|Error)\(\s*"([a-z_]+(?:\.[a-z_]+)+)\"""")


def used_keys() -> set[str]:
    keys: set[str] = set()
    for path in SRC.rglob("*.py"):
        keys.update(KEY_RE.findall(path.read_text(encoding="utf-8")))
    return keys


def test_scanner_finds_keys() -> None:
    keys = used_keys()
    assert "cmd.add.created" in keys
    assert "error.empty_description" in keys


def test_every_used_key_exists_in_en() -> None:
    missing = sorted(key for key in used_keys() if lookup(key) is None)
    assert missing == []


def test_t_formats_params() -> None:
    assert t("cmd.add.created", id=7) == "Created task 7."


def test_t_missing_key_returns_key() -> None:
    assert t("no.such.key") == "no.such.key"
    assert t("cmd.add") == "cmd.add"
