from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tame.__main__ import main
from tame.cli import kindness
from tame.core.service import TaskService
from tame.i18n import lookup

Capture = pytest.CaptureFixture[str]
NOW = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)
HEART = "♥"


class _Fixed:
    def __init__(self, value: float) -> None:
        self.value = value

    def random(self) -> float:
        return self.value

    def shuffle(self, items: list[int]) -> None:
        items.reverse()


def run(capsys: Capture, *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def kind_lines(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith(HEART)]


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend stdout is a terminal, and make every eligible command a lucky one."""
    monkeypatch.setattr(kindness, "is_terminal", lambda: True)
    monkeypatch.setattr(kindness, "_random", _Fixed(0.0))


# --- Phrases and their order -----------------------------------------------------------


def test_fifty_phrases_in_both_languages() -> None:
    for lang in ("en", "fr"):
        texts = [lookup(f"kindness.p{i:02d}", lang) for i in range(1, kindness.COUNT + 1)]
        assert all(texts)
        assert len(set(texts)) == kindness.COUNT
        assert all(len(text) <= 110 for text in texts if text)  # about one terminal line


def test_all_phrases_before_any_repeat(service: TaskService) -> None:
    first = [kindness.draw(service, NOW) for _ in range(kindness.COUNT)]
    assert len(set(first)) == kindness.COUNT
    assert kindness.draw(service, NOW) in first  # a new order starts


def test_corrupt_state_starts_a_new_order(service: TaskService) -> None:
    service.set_state("kindness_order", "not json")
    assert kindness.draw(service, NOW)


def test_cooldown_then_chance(service: TaskService, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kindness, "_random", _Fixed(0.0))
    assert kindness.is_due(service, NOW)  # never shown yet
    kindness.draw(service, NOW)
    assert not kindness.is_due(service, NOW + timedelta(days=2, hours=23))
    assert kindness.is_due(service, NOW + kindness.COOLDOWN)
    monkeypatch.setattr(kindness, "_random", _Fixed(kindness.CHANCE))
    assert not kindness.is_due(service, NOW + kindness.COOLDOWN)


# --- In the CLI -------------------------------------------------------------------------


@pytest.mark.usefixtures("terminal")
def test_after_an_everyday_command(capsys: Capture) -> None:
    run(capsys, "add", "x")
    out = run(capsys, "list")[1]
    assert len(kind_lines(out)) <= 1  # `add` may already have taken the turn
    code, out, _ = run(capsys, "list")
    assert code == 0
    assert kind_lines(out) == []  # cooldown


@pytest.mark.usefixtures("terminal")
def test_first_lucky_command_shows_one(capsys: Capture) -> None:
    out = run(capsys, "add", "x")[1]
    assert out.startswith("Created task 1.\n\n")
    (line,) = kind_lines(out)
    assert line.startswith(f"{HEART} ")


@pytest.mark.usefixtures("terminal")
def test_never_after_errors_or_other_commands(capsys: Capture) -> None:
    assert kind_lines(run(capsys, "version")[1]) == []
    assert kind_lines(run(capsys, "nothing")[1]) == []  # exit 2
    assert kind_lines(run(capsys, "status:all", "export")[1]) == []


def test_never_when_output_is_not_a_terminal(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kindness, "_random", _Fixed(0.0))
    run(capsys, "add", "x")
    assert kind_lines(run(capsys, "1", "done")[1]) == []


@pytest.mark.usefixtures("terminal")
def test_setting_turns_them_off(capsys: Capture) -> None:
    run(capsys, "config", "set", "kindness", "false")
    assert kind_lines(run(capsys, "add", "x")[1]) == []
    assert kind_lines(run(capsys, "1", "done")[1]) == []


def test_when_done_empties_the_list(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kindness, "is_terminal", lambda: True)
    monkeypatch.setattr(kindness, "_random", _Fixed(1.0))  # no random ones
    run(capsys, "add", "a")
    run(capsys, "add", "b")
    assert kind_lines(run(capsys, "1", "done")[1]) == []  # one task left
    out = run(capsys, "1", "done")[1]
    assert out.startswith("Completed task 1 'b'.\n\n")
    assert len(kind_lines(out)) == 1


def test_in_french(capsys: Capture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kindness, "is_terminal", lambda: True)
    monkeypatch.setattr(kindness, "_random", _Fixed(0.0))
    run(capsys, "config", "set", "language", "fr")
    (line,) = kind_lines(run(capsys, "add", "x")[1])
    texts = {lookup(f"kindness.p{i:02d}", "fr") for i in range(1, kindness.COUNT + 1)}
    assert line.removeprefix(f"{HEART} ") in texts


def test_at_the_foot_of_a_printed_page(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("webbrowser.open", lambda url: True)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    run(capsys, "add", "x")
    run(capsys, "print")
    (page,) = tmp_path.glob("tame-print-*.html")
    assert f'<p class="kind">{HEART} ' in page.read_text(encoding="utf-8")
    saved = tmp_path / "saved.html"
    run(capsys, "print", "--file", str(saved))
    assert 'class="kind"' not in saved.read_text(encoding="utf-8")
    run(capsys, "config", "set", "kindness", "false")
    run(capsys, "print", "--file", str(saved))
    for old in tmp_path.glob("tame-print-*.html"):
        old.unlink()
    run(capsys, "print")
    (page,) = tmp_path.glob("tame-print-*.html")
    assert 'class="kind"' not in page.read_text(encoding="utf-8")
