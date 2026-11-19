import re
import tomllib
from pathlib import Path

import tame
from tame.i18n import lookup, t

SRC = Path(tame.__file__).parent
# Any dotted string literal ("cmd.add.created") whose first part is a catalog section:
# catches t("...") calls, TameError keys and keys passed around as arguments.
KEY_RE = re.compile(r'"([a-z_]+(?:\.[a-z_]+)+)"')
SECTIONS = frozenset(tomllib.loads((SRC / "locales" / "en.toml").read_text(encoding="utf-8")))


def used_keys() -> set[str]:
    keys: set[str] = set()
    for path in SRC.rglob("*.py"):
        found = KEY_RE.findall(path.read_text(encoding="utf-8"))
        keys.update(key for key in found if key.split(".")[0] in SECTIONS)
    return keys


def test_scanner_finds_keys() -> None:
    keys = used_keys()
    assert "cmd.add.created" in keys
    assert "error.empty_description" in keys
    assert "confirm.delete.one" in keys


def test_every_used_key_exists_in_en() -> None:
    missing = sorted(key for key in used_keys() if lookup(key) is None)
    assert missing == []


def test_t_formats_params() -> None:
    assert t("cmd.add.created", id=7) == "Created task 7."


def test_t_missing_key_returns_key() -> None:
    assert t("no.such.key") == "no.such.key"
    assert t("cmd.add") == "cmd.add"
