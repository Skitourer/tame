"""Spoilers below are kept in ROT13, like in the code."""

import codecs
import io
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from tame.__main__ import main
from tame.cli import eggs
from tame.core.models import Status
from tame.storage.repo import DB_FILENAME, TaskRepo

Capture = pytest.CaptureFixture[str]


def r(text: str) -> str:
    return codecs.decode(text, "rot13")


def run(capsys: Capture, line: str) -> tuple[int, str, str]:
    code = main(r(line).split())
    out, err = capsys.readouterr()
    return code, out, err


class _Always:
    def random(self) -> float:
        return 0.0


def test_one(capsys: Capture) -> None:
    assert run(capsys, "znxr zr n fnaqjvpu") == (0, r("Jung? Znxr vg lbhefrys.") + "\n", "")
    assert main(["status:all", "list"]) == 2  # nothing created
    capsys.readouterr()


def test_two(capsys: Capture) -> None:
    assert run(capsys, "FHQB znxr zr n fnaqjvpu") == (0, r("Bxnl.") + "\n", "")
    out = run(capsys, "yvfg")[1]
    assert r("Znxr n fnaqjvpu") in out
    assert " H " in out


def test_three(capsys: Capture) -> None:
    code, out, _ = run(capsys, "hc hc qbja qbja yrsg evtug yrsg evtug o n")
    assert code == 0
    assert r("+30 yvirf.") in out
    assert len(out.splitlines()) == 6


def test_four(capsys: Capture) -> None:
    main(["add", "a"])
    main(["add", "b"])
    main(["1", "done"])
    capsys.readouterr()
    code, out, _ = run(capsys, "gnzr")
    assert code == 0
    assert r("1 reenaq gnzrq, 1 fgvyy ebnzvat.") in out
    main(["1", "done"])  # the last pending task, renumbered 1
    capsys.readouterr()
    assert r("2 reenaqf gnzrq, 0 fgvyy ebnzvat.") in run(capsys, "gnzr")[1]


def test_five(capsys: Capture, tame_home: Path) -> None:
    main(["add", "x"])
    with TaskRepo(tame_home / DB_FILENAME) as repo, repo.transaction():
        (task,) = repo.by_status(Status.PENDING)
        repo.update(replace(task, id=42))
    capsys.readouterr()
    out = run(capsys, "42 qbar")[1]
    assert out.splitlines() == [
        "Completed task 42 'x'.",
        r("Gur Nafjre. Abj, jung jnf gur Dhrfgvba?"),
    ]
    main(["add", "y"])
    out = run(capsys, "1 qbar")[1]
    assert r("Gur Nafjre. Abj, jung jnf gur Dhrfgvba?") not in out


def test_six(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    assert run(capsys, "haqb") == (2, "", "Nothing to undo.\n")
    monkeypatch.setattr(eggs, "_random", _Always())
    code, _, err = run(capsys, "haqb")
    assert code == 2
    assert err.splitlines()[0] == "Nothing to undo."
    assert err.splitlines()[1] == r("Terng Fpbgg! Lbh'q arrq 1.21 tvtnjnggf gb tb onpx shegure.")


def test_seven(capsys: Capture) -> None:
    code, out, _ = run(capsys, "ybir")
    assert code == 0
    lines = out.splitlines()
    assert len(lines) == 11  # 7 lines of art, blank line, kind word, blank line, hint
    assert lines[8].startswith("\u2665 ")
    assert lines[10] == r("Jnag n erzvaqre?  gx nqq Pnyy fbzrbar V ybir +ybir qhr:gbqnl")
    run(capsys, "pbasvt frg xvaqarff snyfr")
    assert run(capsys, "ybir")[1].splitlines()[8].startswith("\u2665 ")  # asked for: always


def test_ordinary_lines_are_untouched(capsys: Capture) -> None:
    assert not eggs.hatch([])
    assert not eggs.hatch(["list"])
    assert run(capsys, "nqq fnaqjvpu")[1] == "Created task 1.\n"


class _Fixed:
    def __init__(self, value: float) -> None:
        self.value = value

    def random(self) -> float:
        return self.value


@pytest.mark.parametrize(("value", "shown"), [(0.19, True), (0.2, False), (0.5, False)])
def test_six_odds(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch, value: float, shown: bool
) -> None:
    monkeypatch.setattr(eggs, "_random", _Fixed(value))
    too_far = r("Terng Fpbgg! Lbh'q arrq 1.21 tvtnjnggf gb tb onpx shegure.")
    assert (too_far in run(capsys, "haqb")[2]) is shown


# --- colors (fixed egg.* roles, never themed) ---------------------------------------


def test_caption_splits_drawing_and_text() -> None:
    assert eggs._caption(" (o o)     Hi there.", "egg.art") == [
        (" (o o)", "egg.art"),
        ("     ", None),
        ("Hi there.", "egg.caption"),
    ]
    assert eggs._caption("  `-'", "egg.art") == [("  `-'", "egg.art")]


def test_lasso_colors_rope_figure_and_numbers() -> None:
    assert eggs._lasso("  o   ~~~/") == [("  o   ", "egg.figure"), ("~~~/", "egg.rope")]
    assert eggs._lasso(r" / \     3 of 12") == [
        (" / \\", "egg.figure"),
        ("     ", None),
        ("3", "egg.number"),
        (" of ", None),
        ("12", "egg.number"),
    ]


def test_sentences_and_sparks() -> None:
    assert eggs._sentences("Wow! It takes 2.5 tons here.", "egg.shout", None) == [
        ("Wow!", "egg.shout"),
        (" It takes ", None),
        ("2.5 tons", "egg.spark"),
        (" here.", None),
    ]
    assert eggs._sentences("Just one.", "egg.strong", "egg.soft") == [("Just one.", "egg.strong")]


def test_gradient_goes_top_to_bottom() -> None:
    roles = [line[0][1] for line in eggs._gradient(["a"] * 7)]
    assert roles[0] == "egg.heart1" and roles[-1] == "egg.heart4"
    assert roles == sorted(roles)


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_colored_and_framed_in_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("tame.cli.shellprofile.is_terminal", lambda: False)
    out = _Terminal()
    real = sys.stdout
    sys.stdout = out
    try:
        assert main(r("ybir").split()) == 0
    finally:  # By hand: monkeypatch.undo() would also drop TAME_HOME.
        sys.stdout = real
    text = out.getvalue()
    assert text.startswith("\n") and text.endswith("\n\n")
    assert "\x1b[1;31m" in text  # top of the drawing, bold red
    assert "\x1b[36m" in text  # the command in the hint
