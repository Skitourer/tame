"""Small extras. Spoilers below are kept in ROT13 on purpose."""

import base64
import codecs
import hashlib
import random
import sys
import zlib
from collections.abc import Sequence

from tame.core.models import Task

_TABLE: dict[str, tuple[int, str]] = {
    "5b875159ff617ff8": (0, "Jung? Znxr vg lbhefrys."),
    "32b07f20228f8532": (1, "Bxnl."),
    "22d61fc1428698ff": (
        2,
        "eNoViTEKgDAMAPe84rYmGI3ga4QMXToIgoOgi4+3vbvtAMd7gmvmF2EuqnB1MRM0YYcwBtO2ch5PuxeBmrxEkTHq"
        "XH4ewA6v",
    ),
    "77cf9a363c0fb1f0": (
        3,
        "eNpTUMhXUFCogwN9LgX9mph4EKUQowAC1Qa1CqlFRYl5KdVGtQolibmpKToK1Ya1CsUlmTk5CkX5ibmZeel6AD8PF3A=",
    ),
    "686f746a95b6f836": (
        4,
        "eNpTUNCzsrLSU1CA0FwKVhCgB6XhAlZwAXUUvjoXUK86KhcmAOWAuOoALvUTgQ==",
    ),
}
_FORTY_TWO = "Gur Nafjre. Abj, jung jnf gur Dhrfgvba?"
_TOO_FAR = "Terng Fpbgg! Lbh'q arrq 1.21 tvtnjnggf gb tb onpx shegure."
_ITEM = "Znxr n fnaqjvpu"
_HINT = "Jnag n erzvaqre?  gx nqq Pnyy fbzrbar V ybir +ybir qhr:gbqnl"

_random = random.Random()


def _r(text: str) -> str:
    return codecs.decode(text, "rot13")


def _z(blob: str) -> str:
    return zlib.decompress(base64.b64decode(blob)).decode()


def _key(argv: Sequence[str]) -> str:
    return hashlib.sha256(" ".join(argv).lower().encode()).hexdigest()[:16]


def hatch(argv: Sequence[str]) -> bool:
    """Handle a few special command lines; return True if one was handled."""
    entry = _TABLE.get(_key(argv)) if argv else None
    if entry is None:
        return False
    kind, data = entry
    if kind == 4:
        _heart(data)
        return True
    if kind in (1, 3):
        from tame.cli.commands import open_service
        from tame.config import load_settings
        from tame.core.dates import parse_date, utc_now
        from tame.core.filters import Filter
        from tame.core.models import Status

        with open_service(load_settings()) as service:
            if kind == 1:
                today = parse_date("today", utc_now())
                service.add(_r(_ITEM), priority="H", due=today)
            else:
                done = len(service.query(Filter(status=Status.COMPLETED)))
                pending = len(service.query())
                data = _z(data).format(done, pending, "" if done == 1 else "s")
    print(_z(data) if kind == 2 else data if kind == 3 else _r(data))
    return True


def _heart(data: str) -> None:
    from tame.cli import kindness
    from tame.cli.commands import open_service
    from tame.config import load_settings
    from tame.core.dates import utc_now

    settings = load_settings()
    with open_service(settings) as service:
        word = kindness.draw(service, utc_now())
    print(_z(data))
    kindness.show(word)
    print(_r(_HINT))


def after_done(tasks: Sequence[Task]) -> None:
    """Called after ``done`` with the tasks as they were before."""
    if any(task.id == 42 for task in tasks):
        print(_r(_FORTY_TWO))


def after_empty_undo() -> None:
    """Called when ``undo`` has nothing left to undo."""
    if _random.random() < 1 / 5:
        print(_r(_TOO_FAR), file=sys.stderr)
