import io
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from tame.cli import render
from tame.cli.render import (
    ROLES,
    Related,
    due_state,
    format_age,
    format_local,
    format_urgency,
    help_line,
    info_blocks,
    info_lines,
    relative_day,
    summary_line,
)
from tame.core.models import Annotation, Status, Task

Capture = pytest.CaptureFixture[str]


class Terminal(io.StringIO):
    """A stream that says it is a terminal."""

    def isatty(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def fresh_frame(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("NO_COLOR", raising=False)
    render.configure(color=True)
    yield
    render.configure(color=True)


@pytest.mark.parametrize(
    ("age", "text"),
    [
        (timedelta(seconds=-5), "0s"),
        (timedelta(seconds=45), "45s"),
        (timedelta(minutes=12), "12min"),
        (timedelta(hours=3, minutes=59), "3h"),
        (timedelta(days=5), "5d"),
        (timedelta(days=21), "3w"),
        (timedelta(days=120), "4mo"),
        (timedelta(days=800), "2y"),
    ],
)
def test_format_age(age: timedelta, text: str) -> None:
    assert format_age(age) == text


T0 = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)


def test_format_local_is_local_time() -> None:
    assert format_local(T0) == T0.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def local_day(days: int, hour: int = 12) -> datetime:
    """A time ``days`` local calendar days from local today, at ``hour``."""
    today = datetime.now().astimezone().replace(hour=hour, minute=0, second=0, microsecond=0)
    return today + timedelta(days=days)


def task(**fields: object) -> Task:
    values: dict[str, object] = {"uuid": "u-1", "description": "x", "entry": T0, "modified": T0}
    return Task(**(values | fields))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("due", "state"),
    [
        (None, None),
        (local_day(-1, hour=23), "overdue"),
        (local_day(0, hour=0), "today"),
        (local_day(0, hour=23), "today"),
        (local_day(1, hour=0), None),
    ],
)
def test_due_state(due: datetime | None, state: str | None) -> None:
    assert due_state(task(due=due), local_day(0)) == state


@pytest.mark.parametrize(("value", "text"), [(0.0, "0.0"), (8.04, "8.0"), (12.96, "13.0")])
def test_format_urgency(value: float, text: str) -> None:
    assert format_urgency(value) == text


@pytest.mark.parametrize(
    ("days", "due", "text"),
    [
        (0, False, "today"),
        (-1, False, "yesterday"),
        (1, False, "tomorrow"),
        (-3, False, "3 days ago"),
        (4, False, "in 4 days"),
        (-1, True, "overdue by 1 day"),
        (-2, True, "overdue by 2 days"),
        (2, True, "in 2 days"),
    ],
)
def test_relative_day(days: int, due: bool, text: str) -> None:
    assert relative_day(local_day(days), local_day(0), due=due) == text


def test_description_cell_keeps_markup_and_counts_notes() -> None:
    assert render.description_cell(task(description="[bold]x")).plain == "[bold]x"
    noted = task(annotations=(Annotation(T0, "a"), Annotation(T0, "b")))
    cell = render.description_cell(noted)
    assert cell.plain == "x [2]"
    assert [str(span.style) for span in cell.spans] == [ROLES["note"]]


def test_summary_line_counts_overdue_and_today() -> None:
    now = local_day(0)
    tasks = [task(due=local_day(-2)), task(due=local_day(0)), task(due=local_day(-1)), task()]
    assert summary_line(4, tasks, now) == [
        ("4 tasks", "summary"),
        (" · ", "summary"),
        ("2 overdue", "due.overdue"),
        (" · ", "summary"),
        ("1 due today", "due.today"),
    ]
    assert summary_line(1, tasks[3:], now) == [("1 task", "summary")]
    assert summary_line(2, tasks[3:] * 3, now) == [("2 of 3 tasks", "summary")]


def test_info_blocks_group_fields_and_leave_out_unset_ones() -> None:
    done = task(
        description="Call bank",
        status=Status.COMPLETED,
        end=T0,
        annotations=(Annotation(T0, "call back"), Annotation(T0, "again")),
        depends=frozenset({"u-3", "u-2"}),
        extra={"annotations": [{"description": "note"}], "wait": "20261201T000000Z"},
    )
    paint = task(uuid="u-2", id=2, description="Buy paint")
    gone = task(uuid="u-4", id=None, description="Old", status=Status.DELETED)
    waiting = task(uuid="u-5", id=5, description="Paint walls")
    related = Related(depends=[paint, gone, "u-3xxxxxxxxx"], blocking=[waiting])
    blocks = info_blocks(done, T0, virtual=frozenset({"BLOCKED", "ANNOTATED"}), related=related)
    labels = [[label for label, _ in block] for block in blocks]
    assert labels == [
        ["Status", "Tags", "Urgency", "Depends on", "", "", "Blocking"],
        ["Entered", "Modified", "Ended"],
        ["Notes", ""],
        ["UUID", "annotations", "wait"],
    ]
    lines = [
        (label, "".join(text for text, _ in value)) for block in blocks for label, value in block
    ]
    values = dict(lines)
    assert values["Tags"] == "ANNOTATED BLOCKED"
    assert lines[3:7] == [
        ("Depends on", "2 'Buy paint'"),
        ("", "u-4 'Old'"),
        ("", "u-3xxxxx  (missing)"),
        ("Blocking", "5 'Paint walls'"),
    ]
    assert values["Ended"] == f"{format_local(T0)}  today"
    assert values["Notes"] == f"{format_local(T0)}  call back"
    assert values["annotations"] == '[{"description": "note"}]'


def test_info_due_carries_the_alert_until_done() -> None:
    now = local_day(0)
    late = task(due=local_day(-2), tags=frozenset({"phone"}), project="home", priority="H")
    blocks = info_blocks(late, now, virtual=frozenset({"OVERDUE"}))
    fields = {label: value for block in blocks for label, value in block}
    assert fields["Due"][0][1] == "due.overdue"
    assert fields["Due"][1] == ("  overdue by 2 days", "due.overdue")
    assert fields["Tags"] == [("phone", "tag"), ("   OVERDUE", "note")]
    assert fields["Project"] == [("home", "project")]
    assert fields["Priority"] == [("H", "pri.H")]
    finished = task(due=local_day(-2), status=Status.COMPLETED, end=now)
    due = {label: value for block in info_blocks(finished, now) for label, value in block}["Due"]
    assert due == [(format_local(local_day(-2)), None), ("  2 days ago", "note")]


def test_info_lines_title_rule_and_aligned_labels() -> None:
    lines = [["".join(text for text, _ in line)] for line in info_lines(task(id=4), T0)]
    text = [line[0] for line in lines]
    assert text[0] == "Task 4  x"
    assert set(text[1]) == {"─"}
    assert text[2].startswith("  Status  pending")  # right-aligned on "Modified"
    no_id = info_lines(task(), T0)
    assert no_id[0][0] == ("Task u-1", "header")


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Examples:", [("Examples", "heading"), (":", None), ("", None)]),
        ("Exemples :", [("Exemples", "heading"), (" :", None), ("", None)]),
        (
            "Usage: tk add <description>",
            [("Usage", "heading"), (":", None), (" tk add <description>", "command")],
        ),
        (
            "  tk add Call bank +phone",
            [("  ", None), ("tk add Call bank +phone", "command"), ("", None)],
        ),
        (
            "     tk next                    only the most urgent",
            [
                ("     ", None),
                ("tk next", "command"),
                ("                    only the most urgent", None),
            ],
        ),
        (
            "  add       Create a task",
            [("  ", None), ("add", "command"), ("       Create a task", None)],
        ),
        ("  other words          text", [("  other words          text", None)]),
        (
            "Make it what tk alone runs: tk config",
            [("Make it what tk alone runs: tk config", None)],
        ),
        (
            "Waiting tasks (wait: in the future) are",
            [("Waiting tasks (wait: in the future) are", None)],
        ),
        ("Without status:, only pending tasks", [("Without status:, only pending tasks", None)]),
        ("wait: hides the task", [("wait: hides the task", None)]),
    ],
)
def test_help_line(line: str, expected: list[tuple[str, str | None]]) -> None:
    assert help_line(line, commands={"add"}, command_labels={"Usage"}) == expected


# --- modes, frame and messages -------------------------------------------------------


def test_plain_output_has_no_frame_or_symbols(capsys: Capture) -> None:
    render.success("Created task 1.")
    render.error("No matches.")
    render.close_frame()
    assert capsys.readouterr() == ("Created task 1.\n", "No matches.\n")


def test_terminal_output_is_framed_with_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    out, err = Terminal(), Terminal()
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)
    render.configure(color=False)
    render.success("Created task 1.")
    render.hint("Nothing changed.")
    render.warning("Careful.")
    render.close_frame()
    assert out.getvalue() == "\n✓ Created task 1.\nNothing changed.\n"
    assert err.getvalue() == "! Careful.\n\n"  # closed on the stream written last


def test_colors_need_a_terminal_the_setting_and_no_no_color(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal = Terminal()
    assert render.colors_on(terminal)
    assert not render.colors_on(io.StringIO())
    render.configure(color=False)
    assert not render.colors_on(terminal)
    render.configure(color=True)
    monkeypatch.setenv("NO_COLOR", "1")
    assert not render.colors_on(terminal)
    monkeypatch.setenv("NO_COLOR", "")
    assert render.colors_on(terminal)


def test_colored_error_in_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    err = Terminal()
    monkeypatch.setattr("sys.stderr", err)
    render.error("No matches.")
    text = err.getvalue()
    assert text.startswith("\n") and "✗ " in text and "No matches." in text
    assert "\x1b[" in text  # ANSI styles


def test_ask_prefixes_the_question_in_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdout", Terminal())
    prompts: list[str] = []
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or "y")
    render.configure(color=False)
    assert render.ask("Delete task 1 'x'?") == "y"
    assert prompts == ["? Delete task 1 'x'? (y/N) "]
