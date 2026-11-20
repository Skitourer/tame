"""Datetime encoding shared by the repository and the migrations (SPEC §3)."""

from datetime import UTC, datetime


def to_db(value: datetime) -> str:
    """Format an aware datetime as UTC ISO 8601, e.g. ``2026-11-19T09:30:00Z``."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_db(value: str) -> datetime:
    """Parse a datetime written by :func:`to_db` into an aware UTC datetime."""
    return datetime.fromisoformat(value).astimezone(UTC)
