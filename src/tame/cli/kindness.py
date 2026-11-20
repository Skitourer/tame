"""Kind words (SPEC §5): now and then, a line about the people around us.

Phrases live in the locales as lists, one per pool (``kindness.<pool>``); their length
is read from English, so adding phrases needs no code change. Each pool comes in its
own shuffled order, all of its phrases before any repeat:

- ``empty``: when ``done`` empties the list;
- ``general``: after an everyday command, in a terminal only, at most once every
  ``COOLDOWN`` and then with a ``CHANCE`` per command; at the foot of a ``print`` page;
  in an easter egg (see ``eggs``);
- ``reminders``: a ``tk add … +love`` line suggested by that easter egg.

The ``kindness`` setting turns the first two pools off, but for the egg. State (last
time shown, remaining order per pool) lives in the ``meta`` table, outside undo.
"""

import json
import random
import sys
from datetime import datetime, timedelta
from typing import Literal

from tame.core.service import TaskService
from tame.i18n import phrases

Pool = Literal["empty", "general", "reminders"]
POOLS: tuple[Pool, ...] = ("empty", "general", "reminders")
COOLDOWN = timedelta(days=3)
CHANCE = 1 / 10
HEART = "♥"
ELIGIBLE = frozenset(
    {"list", "next", "add", "done", "delete", "modify", "annotate", "denotate", "info", "undo"}
)
"""Commands after which a kind word may appear."""

_LAST = "kindness_last"
_ORDER = "kindness_order"
_random = random.Random()


def is_terminal() -> bool:
    """Return True if stdout is a terminal (never write kind words into files or pipes)."""
    return sys.stdout.isatty()


def pool(name: Pool) -> tuple[str, ...]:
    """Return the phrases of pool ``name`` in the interface language."""
    return phrases(f"kindness.{name}")


def draw(service: TaskService, now: datetime, name: Pool = "general") -> str:
    """Return the next phrase of pool ``name``, remember it, and restart the cooldown."""
    service.set_state(_LAST, now.isoformat())
    return _next(service, name)


def reminder(service: TaskService) -> str:
    """Return the next ``love`` reminder (a ``tk add`` line); the cooldown is left alone."""
    return _next(service, "reminders")


def _next(service: TaskService, name: Pool) -> str:
    """Pop the next phrase of ``name`` from its shuffled order; a new order starts when empty.

    Indices beyond the pool (phrases removed) are dropped; phrases added later join
    from the next order on.
    """
    texts = pool(name)
    key = f"{_ORDER}.{name}"
    try:
        order = [int(i) for i in json.loads(service.state(key) or "[]")]
        order = [i for i in order if 0 <= i < len(texts)]
    except (ValueError, TypeError):
        order = []
    if not order:
        order = list(range(len(texts)))
        _random.shuffle(order)
    index = order.pop()
    service.set_state(key, json.dumps(order))
    return texts[index]


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


def show(text: str) -> None:
    """Print ``text`` after a blank line, with the heart, in italics when colors are on."""
    from tame.cli import render

    render.emit([[], [(f"{HEART} {text}", "kind")]])
