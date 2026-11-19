"""User-facing text lookup (SPEC §7).

Messages live in ``locales/<lang>.toml``. ``en.toml`` is the reference: a key missing
from the active language falls back to English. The active language is set once at
startup with :func:`set_language`.
"""

import tomllib
from functools import cache
from importlib.resources import files
from typing import Any

DEFAULT_LANGUAGE = "en"

_language = DEFAULT_LANGUAGE


@cache
def _catalog(lang: str) -> dict[str, Any]:
    text = files("tame").joinpath("locales", f"{lang}.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


def set_language(lang: str) -> None:
    """Make ``lang`` the UI language; unknown codes select English."""
    global _language
    _language = lang if lang in available_languages() else DEFAULT_LANGUAGE


def current_language() -> str:
    """Return the active UI language code."""
    return _language


def t(key: str, **params: object) -> str:
    """Return the UI text for ``key`` with ``params`` substituted.

    Args:
        key: Dotted key into the locale file, e.g. ``"cmd.add.created"``.
        **params: Values for the ``{placeholders}`` of the message.

    Returns:
        The formatted message in the active language (English if the key is not
        translated), or ``key`` itself if it is missing from the English catalog.
    """
    message = lookup(key)
    return key if message is None else message.format(**params)


def lookup(key: str, lang: str | None = None) -> str | None:
    """Return the raw message template for ``key``, or None if it is missing.

    Args:
        key: Dotted key into the locale file.
        lang: Language to look in; defaults to the active one. English is the fallback.
    """
    lang = lang or _language
    message = _find(_catalog(lang), key)
    if message is None and lang != DEFAULT_LANGUAGE:
        message = _find(_catalog(DEFAULT_LANGUAGE), key)
    return message


def _find(catalog: dict[str, Any], key: str) -> str | None:
    node: Any = catalog
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


@cache
def available_languages() -> tuple[str, ...]:
    """Return the codes of the bundled UI languages, sorted (e.g. ``("en", "fr")``)."""
    locales = files("tame").joinpath("locales")
    return tuple(
        sorted(p.name.removesuffix(".toml") for p in locales.iterdir() if p.name.endswith(".toml"))
    )
