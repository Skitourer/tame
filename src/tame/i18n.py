"""User-facing text lookup (SPEC §7).

Minimal version: English catalog only. Language selection and fallback come with
the config in roadmap step 7.
"""

import tomllib
from functools import cache
from importlib.resources import files
from typing import Any


@cache
def _catalog(lang: str) -> dict[str, Any]:
    text = files("tame").joinpath("locales", f"{lang}.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


def t(key: str, **params: object) -> str:
    """Return the UI text for ``key`` with ``params`` substituted.

    Args:
        key: Dotted key into the locale file, e.g. ``"cmd.add.created"``.
        **params: Values for the ``{placeholders}`` of the message.

    Returns:
        The formatted message, or ``key`` itself if it is missing from the catalog.
    """
    message = lookup(key)
    return key if message is None else message.format(**params)


def lookup(key: str) -> str | None:
    """Return the raw message template for ``key``, or None if it is missing."""
    node: Any = _catalog("en")
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None
