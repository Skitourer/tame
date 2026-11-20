import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tame.__main__ import main
from tame.cli import kindness
from tame.cli.parser import parse_add
from tame.core.service import TaskService
from tame.i18n import phrases

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


@pytest.mark.parametrize(("name", "size"), [("empty", 15), ("general", 50), ("reminders", 50)])
def test_pools_in_both_languages(name: kindness.Pool, size: int) -> None:
    for lang in ("en", "fr"):
        texts = phrases(f"kindness.{name}", lang)
        assert len(texts) >= size
        assert len(set(texts)) == len(texts)
        assert all(text and len(text) <= 110 for text in texts)  # about one terminal line


def test_pools_do_not_overlap() -> None:
    for lang in ("en", "fr"):
        empty, general = phrases("kindness.empty", lang), phrases("kindness.general", lang)
        assert set(empty).isdisjoint(general)


_RELATIVES = {
    "en": re.compile(
        r"\b(mum|mom|dad|mother|father|parents?|brothers?|sisters?|sons?|daughters?|"
        r"child|children|kids?|grand\w+|cousins?|aunts?|uncles?|godchild|wife|husband|"
        r"partner|my love)\b",
        re.IGNORECASE,
    ),
    "fr": re.compile(
        r"\b(maman|papa|mère|père|parents|frères?|sœurs?|fils|filles?|enfants?|mamie|"
        r"papi|grands?-\w+|cousine?s?|tantes?|oncles?|filleule?s?|épou\w+|mari|"
        r"conjoint\w*|mon amour)\b",
        re.IGNORECASE,
    ),
}


@pytest.mark.parametrize("name", kindness.POOLS)
@pytest.mark.parametrize("lang", ["en", "fr"])
def test_no_specific_relative(name: kindness.Pool, lang: str) -> None:
    """General relations only: no one who lost a relative should be hurt."""
    texts = phrases(f"kindness.{name}", lang)
    assert [text for text in texts if _RELATIVES[lang].search(text)] == []


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_reminders_are_safe_tk_add_lines(lang: str) -> None:
    for line in phrases("kindness.reminders", lang):
        assert not set(line) & set("'\",;&()$|<>`@#"), line  # pastes into any shell
        words = line.split()
        assert words[:2] == ["tk", "add"], line
        parsed = parse_add(words[2:], NOW)
        assert parsed.tags == ("love",), line
        assert parsed.due is not None, line
        assert parsed.description, line


@pytest.mark.parametrize("name", kindness.POOLS)
def test_all_phrases_before_any_repeat(service: TaskService, name: kindness.Pool) -> None:
    size = len(kindness.pool(name))
    first = [kindness._next(service, name) for _ in range(size)]
    assert len(set(first)) == size
    assert kindness._next(service, name) in first  # a new order starts


def test_pools_keep_their_own_order(service: TaskService) -> None:
    kindness.draw(service, NOW, "empty")
    assert len(json.loads(service.state("kindness_order.empty") or "")) == 14
    assert service.state("kindness_order.general") is None


def test_order_survives_a_change_of_pool_size(
    service: TaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.set_state("kindness_order.general", json.dumps([0, 99, 1]))  # 99: removed phrase
    monkeypatch.setattr(kindness, "pool", lambda name: ("a", "b"))
    assert kindness._next(service, "general") == "b"
    assert kindness._next(service, "general") == "a"


def test_reminder_keeps_the_cooldown(service: TaskService) -> None:
    kindness.reminder(service)
    assert service.state("kindness_last") is None


def test_corrupt_state_starts_a_new_order(service: TaskService) -> None:
    service.set_state("kindness_order.general", "not json")
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
    assert line.removeprefix(f"{HEART} ") in phrases("kindness.general", "fr")


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
