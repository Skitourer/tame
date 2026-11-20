import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

import tame
from tame.i18n import available_languages, current_language, lookup, phrases, set_language, t

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


# --- Languages (roadmap step 7c) ----------------------------------------------------

FIELD_RE = re.compile(r"\{(\w*)")


def catalog_keys(node: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten a catalog to ``{dotted key: message}``."""
    keys: dict[str, str] = {}
    for name, value in node.items():
        if isinstance(value, dict):
            keys |= catalog_keys(value, f"{prefix}{name}.")
        elif isinstance(value, list):  # pools: same length in every language
            keys |= {f"{prefix}{name}[{i}]": item for i, item in enumerate(value)}
        else:
            keys[f"{prefix}{name}"] = value
    return keys


def load_catalog(lang: str) -> dict[str, str]:
    text = (SRC / "locales" / f"{lang}.toml").read_text(encoding="utf-8")
    return catalog_keys(tomllib.loads(text))


TRANSLATIONS = [lang for lang in available_languages() if lang != "en"]


def test_french_is_available() -> None:
    assert available_languages() == ("en", "fr")


@pytest.mark.parametrize("lang", TRANSLATIONS)
def test_translation_has_exactly_the_english_keys(lang: str) -> None:
    en, other = load_catalog("en"), load_catalog(lang)
    assert sorted(other.keys() - en.keys()) == []
    assert sorted(en.keys() - other.keys()) == []


@pytest.mark.parametrize("lang", TRANSLATIONS)
def test_translation_keeps_placeholders(lang: str) -> None:
    en, other = load_catalog("en"), load_catalog(lang)
    wrong = [
        key
        for key, message in other.items()
        if sorted(FIELD_RE.findall(message)) != sorted(FIELD_RE.findall(en[key]))
    ]
    assert wrong == []


def test_set_language_switches_messages() -> None:
    set_language("fr")
    assert current_language() == "fr"
    assert t("cmd.add.created", id=7) == "Tâche 7 créée."


def test_unknown_language_selects_english() -> None:
    set_language("xx")
    assert current_language() == "en"
    assert t("cmd.add.created", id=7) == "Created task 7."


def test_missing_translation_falls_back_to_english(monkeypatch: pytest.MonkeyPatch) -> None:
    catalogs = {"en": {"a": {"b": "English"}, "c": "C"}, "fr": {"c": "Ç"}}
    monkeypatch.setattr("tame.i18n._catalog", catalogs.__getitem__)
    assert lookup("a.b", "fr") == "English"
    assert lookup("c", "fr") == "Ç"
    assert lookup("x", "fr") is None


def test_phrases_fall_back_to_english_item_by_item(monkeypatch: pytest.MonkeyPatch) -> None:
    catalogs = {"en": {"k": {"p": ["a", "b", "c"]}}, "fr": {"k": {"p": ["à", "bé", "cé", "dé"]}}}
    monkeypatch.setattr("tame.i18n._catalog", catalogs.__getitem__)
    assert phrases("k.p", "en") == ("a", "b", "c")
    assert phrases("k.p", "fr") == ("à", "bé", "cé")  # English sets the length
    catalogs["fr"] = {"k": {"p": ["à"]}}
    assert phrases("k.p", "fr") == ("à", "b", "c")
    assert phrases("k.missing", "fr") == ()
