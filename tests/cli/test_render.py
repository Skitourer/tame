from datetime import UTC, datetime, timedelta

import pytest

from tame.cli.render import format_age, format_local, info_rows
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
    assert info_rows(task) == [
        ("UUID", "u-1"),
        ("Description", "Call bank"),
        ("Status", "completed"),
        ("Entered", format_local(T0)),
        ("Modified", format_local(T0)),
        ("Ended", format_local(T0)),
        ("annotations", '[{"description": "note"}]'),
        ("wait", "20261201T000000Z"),
    ]


def test_format_local_is_local_time() -> None:
    assert format_local(T0) == T0.astimezone().strftime("%Y-%m-%d %H:%M:%S")
