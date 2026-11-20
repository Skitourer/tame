"""Small extras. Spoilers below are kept in ROT13 on purpose."""

import base64
import codecs
import hashlib
import random
import re
import sys
import zlib
from collections.abc import Sequence

from tame.cli import render
from tame.cli.render import Line, Segment
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
    match kind:
        case 0:
            render.say(_r(data), "egg.no")
        case 1:
            render.say(_r(data), "egg.yes")
        case 2:
            render.emit([_caption(line, "egg.art") for line in _z(data).split("\n")])
        case _:
            render.emit([_lasso(line) for line in data.split("\n")])
    return True


_CAPTION_RE = re.compile(r"^(.*?)( {3,})([+\w].*)$")  # Text starts with a word or +N.
_ROPE_RE = re.compile(r"(~+/|_/)")
_NUMBER_RE = re.compile(r"(\d+)")


def _caption(line: str, art: str) -> list[Segment]:
    """Split ``line`` into its drawing and the text after it (3+ spaces apart)."""
    if match := _CAPTION_RE.match(line):
        return [(match.group(1), art), (match.group(2), None), (match.group(3), "egg.caption")]
    return [(line, art)]


def _lasso(line: str) -> Line:
    """A drawing with a rope, then a caption whose numbers stand out."""
    caption: list[Segment] = []
    if match := _CAPTION_RE.match(line):
        line, gap, text = match.groups()
        caption = [(gap, None)] + [
            (part, "egg.number" if part.isdigit() else None)
            for part in _NUMBER_RE.split(text)
            if part
        ]
    drawing: list[Segment] = [
        (part, "egg.rope" if _ROPE_RE.fullmatch(part) else "egg.figure")
        for part in _ROPE_RE.split(line)
        if part
    ]
    return drawing + caption


def _gradient(lines: list[str]) -> list[Line]:
    """Color ``lines`` from the first heart role to the last, top to bottom."""
    roles = ["egg.heart1", "egg.heart2", "egg.heart3", "egg.heart4"]
    return [[(line, roles[i * len(roles) // len(lines)])] for i, line in enumerate(lines)]


_SPARK_RE = re.compile(r"(\d+\.\d+ \w+)")


def _sentences(text: str, first: str, rest: str | None) -> list[Segment]:
    """Style the first sentence of ``text`` as ``first``, what follows as ``rest``.

    A number with a unit in what follows (``1.21 xyz``) stands out.
    """
    end = re.search(r"[.!?] ", text)
    cut = end.start() + 1 if end else len(text)
    tail = [
        (part, "egg.spark" if _SPARK_RE.fullmatch(part) else rest)
        for part in _SPARK_RE.split(text[cut:])
        if part
    ]
    return [(text[:cut], first), *tail]


def _heart(data: str) -> None:
    from tame.cli import kindness
    from tame.cli.commands import open_service
    from tame.config import load_settings
    from tame.core.dates import utc_now

    settings = load_settings()
    with open_service(settings) as service:
        word = kindness.draw(service, utc_now())
    render.emit(_gradient(_z(data).split("\n")))
    kindness.show(word)
    text, _, command = _r(_HINT).partition("  ")
    render.emit([[], [(f"{text}  ", None), (command, "command")]])


def after_done(tasks: Sequence[Task]) -> None:
    """Called after ``done`` with the tasks as they were before."""
    if any(task.id == 42 for task in tasks):
        render.emit([_sentences(_r(_FORTY_TWO), "egg.strong", "egg.soft")])


def after_empty_undo() -> None:
    """Called when ``undo`` has nothing left to undo."""
    if _random.random() < 1 / 5:
        render.emit([_sentences(_r(_TOO_FAR), "egg.shout", None)], sys.stderr)
