from datetime import UTC, datetime, timedelta, timezone

import pytest

from tame.core.dates import local_period, parse_date, utc_now
from tame.errors import ValidationError

TZ = timezone(timedelta(hours=1))
NOW = datetime(2026, 11, 19, 9, 30, 15, tzinfo=UTC)  # Thursday 10:30:15 local


def local(*args: int) -> datetime:
    return datetime(*args, tzinfo=TZ).astimezone(UTC)  # type: ignore[misc]


def parse(text: str) -> datetime:
    return parse_date(text, NOW, TZ)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # ISO (SPEC §6 examples): date only = 00:00 local.
        ("2026-12-15", local(2026, 12, 15)),
        ("2026-12-15T14:00", local(2026, 12, 15, 14)),
        ("2026-12-15T14:00Z", datetime(2026, 12, 15, 14, tzinfo=UTC)),
        ("20261215T140000Z", datetime(2026, 12, 15, 14, tzinfo=UTC)),  # TW format
        # Days.
        ("today", local(2026, 11, 19)),
        ("tomorrow", local(2026, 11, 20)),
        ("yesterday", local(2026, 11, 18)),
        ("TODAY", local(2026, 11, 19)),
        # Weekdays: next occurrence, never today.
        ("friday", local(2026, 11, 20)),
        ("fri", local(2026, 11, 20)),
        ("mon", local(2026, 11, 23)),
        ("thursday", local(2026, 11, 26)),
        ("thu", local(2026, 11, 26)),
        ("wed", local(2026, 11, 25)),
        ("sunday", local(2026, 11, 22)),
        # Period ends: last second.
        ("eow", local(2026, 11, 22, 23, 59, 59)),
        ("eom", local(2026, 11, 30, 23, 59, 59)),
        ("eoy", local(2026, 12, 31, 23, 59, 59)),
        # Offsets from now.
        ("+3d", NOW + timedelta(days=3)),
        ("+2w", NOW + timedelta(weeks=2)),
        ("+4h", NOW + timedelta(hours=4)),
        ("-1d", NOW - timedelta(days=1)),
        ("+1m", local(2026, 12, 19, 10, 30, 15)),
        ("+3m", local(2027, 2, 19, 10, 30, 15)),
        ("-11m", local(2025, 12, 19, 10, 30, 15)),
    ],
)
def test_parse_date(text: str, expected: datetime) -> None:
    result = parse(text)
    assert result == expected
    assert result.tzinfo is UTC


def test_month_offset_clamps_to_month_end() -> None:
    jan31 = datetime(2027, 1, 31, 12, tzinfo=TZ)
    assert parse_date("+1m", jan31, TZ) == datetime(2027, 2, 28, 12, tzinfo=TZ)


def test_eow_on_sunday_is_today() -> None:
    sunday = datetime(2026, 11, 22, 8, tzinfo=TZ)
    assert parse_date("eow", sunday, TZ) == datetime(2026, 11, 22, 23, 59, 59, tzinfo=TZ)


def test_local_day_differs_from_utc_day() -> None:
    # 23:30 UTC on the 19th is already the 20th at UTC+1.
    late = datetime(2026, 11, 19, 23, 30, tzinfo=UTC)
    assert parse_date("today", late, TZ) == datetime(2026, 11, 20, tzinfo=TZ)


def test_system_time_zone_by_default() -> None:
    expected = datetime(2026, 12, 15).astimezone()
    assert parse_date("2026-12-15", NOW) == expected


@pytest.mark.parametrize("text", ["", "someday", "+3", "+3y", "3d", "2026-13-01", "fr", "eod"])
def test_invalid_date(text: str) -> None:
    with pytest.raises(ValidationError) as exc:
        parse(text)
    assert (exc.value.key, exc.value.params) == ("error.invalid_date", {"value": text})


def test_utc_now_is_aware_and_second_precision() -> None:
    now = utc_now()
    assert now.tzinfo is not None
    assert now.microsecond == 0


@pytest.mark.parametrize(
    ("unit", "start", "end"),
    [
        ("today", local(2026, 11, 19), local(2026, 11, 20)),
        ("tomorrow", local(2026, 11, 20), local(2026, 11, 21)),
        ("week", local(2026, 11, 16), local(2026, 11, 23)),
        ("month", local(2026, 11, 1), local(2026, 12, 1)),
    ],
)
def test_local_period(unit: str, start: datetime, end: datetime) -> None:
    assert local_period(unit, NOW, TZ) == (start, end)  # type: ignore[arg-type]


def test_local_period_month_rolls_over_year() -> None:
    december = datetime(2026, 12, 31, 12, tzinfo=UTC)
    assert local_period("month", december, TZ) == (local(2026, 12, 1), local(2027, 1, 1))
