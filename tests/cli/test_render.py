from datetime import UTC, datetime, timedelta

import pytest

from tame.cli.render import format_age, format_local, format_urgency, info_rows, row_style
from tame.core.models import Status, Task


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


def test_info_rows_hide_unset_fields_and_show_extra() -> None:
    task = Task(
        uuid="u-1",
        description="Call bank",
        entry=T0,
        modified=T0,
        status=Status.COMPLETED,
        end=T0,
        extra={"annotations": [{"description": "note"}], "wait": "20261201T000000Z"},
    )
    assert info_rows(task, T0) == [
        ("UUID", "u-1"),
        ("Description", "Call bank"),
        ("Status", "completed"),
        ("Entered", format_local(T0)),
        ("Modified", format_local(T0)),
        ("Ended", format_local(T0)),
        ("Urgency", "0.0"),
        ("annotations", '[{"description": "note"}]'),
        ("wait", "20261201T000000Z"),
    ]


def test_format_local_is_local_time() -> None:
    assert format_local(T0) == T0.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def local_day(days: int, hour: int = 12) -> datetime:
    """A time ``days`` local calendar days from local today, at ``hour``."""
    today = datetime.now().astimezone().replace(hour=hour, minute=0, second=0, microsecond=0)
    return today + timedelta(days=days)


@pytest.mark.parametrize(
    ("due", "style"),
    [
        (None, None),
        (local_day(-1, hour=23), "red"),
        (local_day(0, hour=0), "yellow"),
        (local_day(0, hour=23), "yellow"),
        (local_day(1, hour=0), None),
    ],
)
def test_row_style(due: datetime | None, style: str | None) -> None:
    task = Task(uuid="u", description="x", entry=T0, modified=T0, due=due)
    assert row_style(task, local_day(0)) == style


@pytest.mark.parametrize(("value", "text"), [(0.0, "0.0"), (8.04, "8.0"), (12.96, "13.0")])
def test_format_urgency(value: float, text: str) -> None:
    assert format_urgency(value) == text
