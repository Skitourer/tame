"""Date parsing (SPEC §6). Keywords are English only, whatever the UI language.

Results are aware UTC datetimes. Calendar arithmetic happens in local time: by default
the system time zone (DST-aware); tests inject a fixed ``tz``.
"""

import calendar
import re
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import Literal

from tame.errors import ValidationError

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_OFFSET_RE = re.compile(r"([+-])(\d+)([hdwm])")
_END_OF_DAY = time(23, 59, 59)


def utc_now() -> datetime:
    """Return the current UTC time, truncated to the second (storage precision)."""
    return datetime.now(UTC).replace(microsecond=0)


def parse_date(text: str, now: datetime, tz: tzinfo | None = None) -> datetime:
    """Parse a user date relative to ``now``.

    Forms (case-insensitive):

    - ISO: ``2026-12-15`` (00:00 local), ``2026-12-15T14:00``; an explicit offset is kept.
    - ``today``, ``tomorrow``, ``yesterday``: 00:00 local.
    - ``monday``..``sunday``, ``mon``..``sun``: next occurrence at 00:00, never today.
    - ``eow``, ``eom``, ``eoy``: last second of the week (Sunday), month or year.
    - ``+3d``, ``+2w``, ``+1m``, ``+4h``, ``-1d``: offset from ``now``; months are
      calendar months, clamped to the last day of a shorter month.

    Args:
        text: The date as typed.
        now: Current aware time.
        tz: Local time zone; None means the system one.

    Returns:
        An aware UTC datetime, to the second.

    Raises:
        ValidationError: If ``text`` is not a date.
    """
    word = text.strip().lower()
    local_now = now.astimezone(tz).replace(tzinfo=None)
    today = local_now.date()
    result: datetime | None = None

    if word in ("today", "tomorrow", "yesterday"):
        delta = {"today": 0, "tomorrow": 1, "yesterday": -1}[word]
        result = localize(datetime.combine(today + timedelta(days=delta), time()), tz)
    elif (weekday := _weekday(word)) is not None:
        ahead = (weekday - today.weekday()) % 7 or 7
        result = localize(datetime.combine(today + timedelta(days=ahead), time()), tz)
    elif word in ("eow", "eom", "eoy"):
        result = localize(datetime.combine(_period_end(word, today), _END_OF_DAY), tz)
    elif match := _OFFSET_RE.fullmatch(word):
        count = int(match[2]) * (1 if match[1] == "+" else -1)
        unit = match[3]
        if unit == "m":
            result = localize(add_months(local_now, count), tz)
        else:
            hours = {"h": 1, "d": 24, "w": 24 * 7}[unit] * count
            result = now + timedelta(hours=hours)
    else:
        result = _parse_iso(text.strip(), tz)

    if result is None:
        raise ValidationError("error.invalid_date", value=text)
    return result.astimezone(UTC).replace(microsecond=0)


def local_period(
    unit: Literal["today", "tomorrow", "week", "month"], now: datetime, tz: tzinfo | None = None
) -> tuple[datetime, datetime]:
    """Return the local calendar period around ``now`` as ``[start, end)`` in UTC.

    Weeks run from Monday to Sunday.

    Args:
        unit: The local day today or tomorrow, the current week or month.
        now: Current aware time.
        tz: Local time zone; None means the system one.
    """
    today = now.astimezone(tz).date()
    if unit == "today":
        start, end = today, today + timedelta(days=1)
    elif unit == "tomorrow":
        start, end = today + timedelta(days=1), today + timedelta(days=2)
    elif unit == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)
    else:
        start = today.replace(day=1)
        end = (start + timedelta(days=31)).replace(day=1)
    return (
        localize(datetime.combine(start, time()), tz).astimezone(UTC),
        localize(datetime.combine(end, time()), tz).astimezone(UTC),
    )


def _weekday(word: str) -> int | None:
    for index, name in enumerate(_WEEKDAYS):
        if word in (name, name[:3]):
            return index
    return None


def _period_end(word: str, today: date) -> date:
    if word == "eow":
        return today + timedelta(days=6 - today.weekday())
    if word == "eom":
        return today.replace(day=calendar.monthrange(today.year, today.month)[1])
    return today.replace(month=12, day=31)


def add_months(value: datetime, months: int, day: int | None = None) -> datetime:
    """Return ``value`` moved by calendar ``months``, on ``day`` (default: its own day).

    The day is clamped to the length of the target month (Jan 31 + 1 → Feb 28).
    """
    day = value.day if day is None else day
    index = value.year * 12 + value.month - 1 + months
    year, month = divmod(index, 12)
    day = min(day, calendar.monthrange(year, month + 1)[1])
    return value.replace(year=year, month=month + 1, day=day)


def _parse_iso(text: str, tz: tzinfo | None) -> datetime | None:
    if not text[:1].isdigit():
        return None
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    return value if value.tzinfo else localize(value, tz)


def localize(naive: datetime, tz: tzinfo | None = None) -> datetime:
    """Attach the local zone to a naive local datetime (system zone: DST-aware)."""
    return naive.astimezone() if tz is None else naive.replace(tzinfo=tz)
