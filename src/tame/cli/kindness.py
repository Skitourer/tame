"""Kind words (SPEC §5): now and then, a line about the people around us.

Fifty phrases (``kindness.p01``..``p50`` in the locales) come in a shuffled order, all of
them before any repeats. They appear:

- after an everyday command, in a terminal only, at most once every ``COOLDOWN`` and then
  with a ``CHANCE`` per command;
- when ``done`` empties the list;
- at the foot of a ``print`` page;
- in an easter egg (see ``eggs``).

The ``kindness`` setting turns the first three off. State (last time shown, remaining
order) lives in the ``meta`` table, outside undo.
"""

import json
import random
import sys
from datetime import datetime, timedelta

from tame.core.service import TaskService
from tame.i18n import t

COUNT = 50
COOLDOWN = timedelta(days=3)
CHANCE = 1 / 10
HEART = "♥"
ELIGIBLE = frozenset({"list", "next", "add", "done", "delete", "modify", "info", "undo"})
"""Commands after which a kind word may appear."""

_LAST = "kindness_last"
_ORDER = "kindness_order"
_random = random.Random()


def is_terminal() -> bool:
    """Return True if stdout is a terminal (never write kind words into files or pipes)."""
    return sys.stdout.isatty()


def phrase(index: int) -> str:
    """Return phrase ``index`` (0-based) in the interface language."""
    return t(f"kindness.p{index + 1:02d}")


def draw(service: TaskService, now: datetime) -> str:
    """Return the next phrase, remember it, and restart the cooldown.

    Phrases follow a shuffled order; a new order starts once all have been shown.
    """
    try:
        order = [i for i in json.loads(service.state(_ORDER) or "[]") if 0 <= int(i) < COUNT]
    except (ValueError, TypeError):
        order = []
    if not order:
        order = list(range(COUNT))
        _random.shuffle(order)
    index = int(order.pop())
    service.set_state(_ORDER, json.dumps(order))
    service.set_state(_LAST, now.isoformat())
    return phrase(index)


def is_due(service: TaskService, now: datetime) -> bool:
    """Return True if a random kind word should appear now: cooldown over, then by chance."""
    last = service.state(_LAST)
    if last is not None:
        try:
            if now - datetime.fromisoformat(last) < COOLDOWN:
                return False
        except ValueError:
            pass
    return _random.random() < CHANCE


def show(text: str, *, color: bool) -> None:
    """Print ``text`` after a blank line, with the heart, in italics when colors are on."""
    from rich.console import Console
    from rich.text import Text

    Console(highlight=False, no_color=not color).print(
        Text(f"\n{HEART} {text}", style="italic dim"), soft_wrap=True
    )
