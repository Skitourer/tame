"""``start`` / ``stop``, work sessions and time spent (SPEC §5)."""

import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tame.__main__ import main
from tame.cli.render import format_duration
from tame.core.dates import utc_now
from tame.core.models import Annotation, Session, Status
from tame.core.service import TaskService
from tame.errors import ValidationError
from tame.io.tw_json import split_sessions, task_from_tw, task_to_tw
from tame.storage.repo import DB_FILENAME, TaskRepo

Capture = pytest.CaptureFixture[str]


def run(capsys: Capture, *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def backdate(home: Path, description: str, minutes: int) -> None:
    """Pretend the current session of ``description`` started ``minutes`` ago."""
    with TaskRepo(home / DB_FILENAME) as repo:
        task = next(t for t in repo.by_status(Status.PENDING) if t.description == description)
        with repo.transaction():
            repo.update(replace(task, start=utc_now() - timedelta(minutes=minutes)))


def export(capsys: Capture) -> dict[str, dict[str, object]]:
    return {
        task["description"]: task for task in json.loads(run(capsys, "status:all", "export")[1])
    }


@pytest.fixture
def three(capsys: Capture) -> None:
    for name in ("Write report", "Call bank", "Read mail"):
        run(capsys, "add", *name.split())


# --- Durations ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("minutes", "text"),
    [(0, "0min"), (45, "45min"), (60, "1h00"), (80, "1h20"), (24 * 60 + 185, "1d 3h")],
)
def test_format_duration(minutes: int, text: str) -> None:
    assert format_duration(timedelta(minutes=minutes, seconds=30)) == text


# --- Service ----------------------------------------------------------------------


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def test_sessions_add_up(repo: TaskRepo, frozen_now: datetime) -> None:
    clock = Clock(frozen_now)
    service = TaskService(repo, clock=clock)
    task = service.add("Write report")
    (task,) = service.start([task]).started
    clock.now += timedelta(minutes=50)
    ((task, session),) = service.stop([task])
    assert session == Session(frozen_now, frozen_now + timedelta(minutes=50))
    (task,) = service.start([task]).started
    clock.now += timedelta(minutes=25)
    assert task.time_spent(clock.now) == timedelta(minutes=75)  # current session counted
    (task,) = service.complete([task])
    assert task.start is None
    assert [s.duration for s in task.sessions] == [timedelta(minutes=50), timedelta(minutes=25)]
    assert repo.get(task.uuid) == task


def test_one_active_task_by_default(service: TaskService) -> None:
    first, second = service.add("a"), service.add("b")
    service.start([first])
    result = service.start([second])
    assert [task.description for task, _ in result.stopped] == ["a"]
    assert [task.description for task in service.query() if task.active] == ["b"]
    with pytest.raises(ValidationError) as exc:
        service.start([service.add("c"), service.add("d")])
    assert exc.value.key == "error.one_active"


def test_multiple_active_allowed(service: TaskService) -> None:
    service.add("a")
    service.add("b")
    result = service.start(service.query(), multiple_active=True)
    assert len(result.started) == 2
    assert result.stopped == ()


def test_start_twice_and_undo(service: TaskService) -> None:
    task = service.add("a")
    other = service.add("b")
    service.start([other])
    (task,) = service.start([task]).started
    assert service.start([task]).already == (task,)
    assert service.undo().cmd == "start"  # one step: a back to idle, b active again
    states = {t.description: t.active for t in service.query()}
    assert states == {"a": False, "b": True}


# --- CLI ----------------------------------------------------------------------------


@pytest.mark.usefixtures("three")
def test_spec_example_start_then_stop(capsys: Capture, tame_home: Path) -> None:
    assert run(capsys, "1", "start") == (0, "Started task 1 'Write report'.\n", "")
    backdate(tame_home, "Write report", 80)
    out = run(capsys, "list")[1]
    assert out.splitlines()[0].split()[-3:] == ["Active", "Description", "Urg"]
    row = next(line for line in out.splitlines() if "Write report" in line)
    assert " 1h20 " in row
    assert run(capsys, "stop") == (0, "Stopped task 1 'Write report' after 1h20.\n", "")
    assert "Active" not in run(capsys, "list")[1]


@pytest.mark.usefixtures("three")
def test_start_stops_the_active_task(capsys: Capture, tame_home: Path) -> None:
    run(capsys, "1", "start")
    backdate(tame_home, "Write report", 10)
    assert run(capsys, "2", "start")[1] == (
        "Stopped task 1 'Write report' after 10min.\nStarted task 2 'Call bank'.\n"
    )
    assert run(capsys, "2", "start")[1] == "Task 2 'Call bank' is already active.\n"


@pytest.mark.usefixtures("three")
def test_several_at_once_need_the_setting(capsys: Capture) -> None:
    code, _, err = run(capsys, "1,2", "start")
    assert code == 1
    assert err.startswith("Only one task can be active: 2 match")
    run(capsys, "config", "set", "multiple_active", "true")
    assert run(capsys, "1,2", "start")[0] == 0
    assert [line.split()[0] for line in run(capsys, "+ACTIVE", "list")[1].splitlines()[2:4]] == [
        "1",
        "2",
    ]
    assert run(capsys, "2", "stop")[1].startswith("Stopped task 2 'Call bank'")
    assert run(capsys, "stop")[1].startswith("Stopped task 1 'Write report'")


@pytest.mark.usefixtures("three")
def test_stop_with_nothing_active(capsys: Capture) -> None:
    assert run(capsys, "stop") == (2, "", "No active task.\n")
    assert run(capsys, "1", "stop") == (2, "", "No active task.\n")


@pytest.mark.usefixtures("three")
def test_start_needs_a_filter_and_s_is_ambiguous(capsys: Capture) -> None:
    assert run(capsys, "start")[0] == 1
    code, _, err = run(capsys, "s")
    assert code == 1
    assert "start, stop" in err


@pytest.mark.usefixtures("three")
def test_done_keeps_the_time_and_info_shows_it(capsys: Capture, tame_home: Path) -> None:
    run(capsys, "1", "start")
    backdate(tame_home, "Write report", 30)
    out = run(capsys, "1", "info")[1]
    assert "Time spent  30min  (1 session)\n" in out
    assert "ACTIVE" in out
    run(capsys, "1", "done")
    out = run(capsys, "status:completed", "info")[1]
    assert "Time spent  30min  (1 session)\n" in out
    assert "ACTIVE" not in out


@pytest.mark.usefixtures("three")
def test_active_gains_urgency_and_is_reserved(capsys: Capture) -> None:
    run(capsys, "1", "start")
    assert export(capsys)["Write report"]["urgency"] == pytest.approx(4.0, abs=0.1)
    assert run(capsys, "2", "modify", "+ACTIVE")[0] == 1


@pytest.mark.usefixtures("three")
def test_undo_stop(capsys: Capture) -> None:
    run(capsys, "1", "start")
    run(capsys, "stop")
    run(capsys, "undo")
    assert "Active" in run(capsys, "list")[1]


# --- Taskwarrior journal annotations ---------------------------------------------------

T0 = datetime(2026, 11, 2, 8, 0, tzinfo=utc_now().tzinfo)


def test_export_sessions_as_journal_annotations_and_back() -> None:
    from tame.core.models import Task

    task = Task(
        uuid="a1b2c3d4-0000-4000-8000-000000000001",
        description="Write report",
        entry=T0,
        modified=T0,
        annotations=(Annotation(T0 + timedelta(minutes=5), "outline done"),),
        sessions=(Session(T0, T0 + timedelta(hours=1)),),
        start=T0 + timedelta(hours=2),
    )
    data = task_to_tw(task)
    assert [note["description"] for note in data["annotations"]] == [
        "Started task",
        "outline done",
        "Stopped task",
    ]
    back = task_from_tw(data, T0)
    assert back.annotations == task.annotations
    assert back.sessions == task.sessions
    assert back.start == task.start


def test_split_sessions_keeps_odd_journal_notes() -> None:
    notes = [
        Annotation(T0, "Stopped task"),  # no start before it
        Annotation(T0 + timedelta(minutes=1), "Started task"),
        Annotation(T0 + timedelta(minutes=2), "Started task"),  # the first is left alone
        Annotation(T0 + timedelta(minutes=3), "Stopped task"),
        Annotation(T0 + timedelta(minutes=4), "Started task"),  # current session
    ]
    kept, sessions = split_sessions(notes, start=T0 + timedelta(minutes=4))
    assert [note.entry for note in kept] == [T0, T0 + timedelta(minutes=1)]
    assert sessions == (Session(T0 + timedelta(minutes=2), T0 + timedelta(minutes=3)),)
