"""Recurrence periods and next due dates (SPEC §4 Recurrence)."""

import zoneinfo
from datetime import UTC, datetime, timedelta, timezone

import pytest

from tame.core.models import Task
from tame.core.recurrence import (
    ANCHOR,
    Period,
    anchored,
    check_recur,
    next_due,
    parse_period,
    same_period,
)
from tame.errors import ValidationError

TZ = timezone(timedelta(hours=1))


def local(*args: int) -> datetime:
    return datetime(*args, tzinfo=TZ).astimezone(UTC)  # type: ignore[misc]


def task(recur: str | None, due: datetime | None, **extra: object) -> Task:
    moment = datetime(2026, 1, 1, tzinfo=UTC)
    return Task(
        uuid="u",
        description="d",
        entry=moment,
        modified=moment,
        recur=recur,
        due=due,
        extra=dict(extra),
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("daily", Period("days", 1)),
        ("weekly", Period("days", 7)),
        ("biweekly", Period("days", 14)),
        ("monthly", Period("months", 1)),
        ("quarterly", Period("months", 3)),
        ("yearly", Period("months", 12)),
        ("annual", Period("months", 12)),
        ("weekdays", Period("weekdays", 1)),
        ("3d", Period("days", 3)),
        ("2w", Period("days", 14)),
        ("6m", Period("months", 6)),
        ("2y", Period("months", 24)),
        (" Weekly ", Period("days", 7)),
        ("0d", None),
        ("P1W", None),
        ("fortnight", None),
        ("2", None),
        ("", None),
    ],
)
def test_parse_period(text: str, expected: Period | None) -> None:
    assert parse_period(text) == expected


def test_check_recur_lowercases_and_rejects_unknown_periods() -> None:
    assert check_recur("Monthly") == "monthly"
    with pytest.raises(ValidationError) as exc:
        check_recur("P1W")
    assert exc.value.key == "error.invalid_recur"


@pytest.mark.parametrize(
    ("stored", "wanted", "expected"),
    [
        ("biweekly", "2w", True),
        ("2w", "BIWEEKLY", True),
        ("14d", "2w", True),
        ("yearly", "12m", True),
        ("annual", "1y", True),
        ("4w", "1m", False),
        ("weekly", "daily", False),
        ("P1W", "p1w", True),
        ("P1W", "weekly", False),
        (None, "weekly", False),
        (None, "", True),
        ("weekly", "", False),
    ],
)
def test_same_period(stored: str | None, wanted: str, expected: bool) -> None:
    assert same_period(stored, wanted) is expected


def test_anchor_is_kept_for_months_and_years_only() -> None:
    assert anchored(task("monthly", local(2027, 1, 31, 9)), TZ).extra == {ANCHOR: 31}
    assert anchored(task("1y", local(2028, 2, 29)), TZ).extra == {ANCHOR: 29}
    assert anchored(task("weekly", local(2027, 1, 31), **{ANCHOR: 31}), TZ).extra == {}
    assert anchored(task(None, local(2027, 1, 31), **{ANCHOR: 31}), TZ).extra == {}


def test_anchor_uses_the_local_day() -> None:
    late = datetime(2027, 1, 30, 23, 30, tzinfo=UTC)  # Jan 31, 00:30 local
    assert anchored(task("monthly", late), TZ).extra == {ANCHOR: 31}


def test_next_due_adds_the_period_keeping_the_local_time() -> None:
    now = local(2027, 3, 1)
    assert next_due(task("weekly", local(2027, 3, 5, 18)), now, TZ) == local(2027, 3, 12, 18)
    assert next_due(task("3d", local(2027, 3, 5, 18)), now, TZ) == local(2027, 3, 8, 18)


def test_next_due_skips_missed_occurrences() -> None:
    now = local(2027, 3, 20, 12)
    # Due Mar 5; Mar 12 and Mar 19 have passed too: the next one is Mar 26.
    assert next_due(task("weekly", local(2027, 3, 5, 9)), now, TZ) == local(2027, 3, 26, 9)
    # Due on Mar 20 at 12:00 exactly, now: the next one must be after now.
    assert next_due(task("daily", local(2027, 3, 19, 12)), now, TZ) == local(2027, 3, 21, 12)


def test_monthly_series_comes_back_to_its_anchor_day() -> None:
    now = local(2027, 1, 1)
    january = anchored(task("monthly", local(2027, 1, 31, 8)), TZ)
    february = next_due(january, now, TZ)
    assert february == local(2027, 2, 28, 8)
    march = next_due(task("monthly", february, **january.extra), now, TZ)
    assert march == local(2027, 3, 31, 8)
    assert next_due(task("monthly", march, **january.extra), now, TZ) == local(2027, 4, 30, 8)


def test_without_anchor_the_due_day_is_used() -> None:
    assert next_due(task("1m", local(2027, 2, 28)), local(2027, 1, 1), TZ) == local(2027, 3, 28)


def test_yearly_on_february_29() -> None:
    leap = anchored(task("yearly", local(2028, 2, 29)), TZ)
    assert next_due(leap, local(2028, 3, 1), TZ) == local(2029, 2, 28)
    assert next_due(task("yearly", local(2031, 2, 28), **leap.extra), local(2031, 3, 1), TZ) == (
        local(2032, 2, 29)
    )


def test_quarterly_skips_to_the_first_future_quarter() -> None:
    due = anchored(task("quarterly", local(2026, 1, 15)), TZ)
    assert next_due(due, local(2026, 11, 19), TZ) == local(2027, 1, 15)


def test_weekdays_skip_the_weekend() -> None:
    friday = local(2027, 3, 5, 9)
    assert next_due(task("weekdays", friday), local(2027, 3, 1), TZ) == local(2027, 3, 8, 9)
    saturday = local(2027, 3, 6, 9)
    assert next_due(task("weekdays", saturday), local(2027, 3, 1), TZ) == local(2027, 3, 8, 9)
    monday = local(2027, 3, 8, 9)
    assert next_due(task("weekdays", monday), local(2027, 3, 1), TZ) == local(2027, 3, 9, 9)


def test_no_next_due_without_a_known_period_or_a_due() -> None:
    now = local(2027, 1, 1)
    assert next_due(task("P1W", local(2027, 3, 5)), now, TZ) is None
    assert next_due(task("weekly", None), now, TZ) is None
    assert next_due(task(None, local(2027, 3, 5)), now, TZ) is None


def test_local_time_is_kept_across_daylight_saving() -> None:
    try:
        paris = zoneinfo.ZoneInfo("Europe/Paris")
    except zoneinfo.ZoneInfoNotFoundError:
        pytest.skip("no time zone data")
    before = datetime(2027, 3, 26, 9, tzinfo=paris)  # Friday, winter time (UTC+1)
    after = next_due(task("weekly", before.astimezone(UTC)), before.astimezone(UTC), paris)
    assert after is not None
    assert after.astimezone(paris) == datetime(2027, 4, 2, 9, tzinfo=paris)  # summer time
    assert after - before == timedelta(days=7, hours=-1)
