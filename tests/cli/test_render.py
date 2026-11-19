from datetime import timedelta

import pytest

from tame.cli.render import format_age


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
