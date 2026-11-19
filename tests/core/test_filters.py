from datetime import UTC, datetime, timedelta

import pytest

from tame.core.filters import Filter
from tame.core.models import NONE, Priority, Status, Task

T0 = datetime(2026, 11, 19, tzinfo=UTC)


def task(**overrides: object) -> Task:
    fields: dict[str, object] = {
        "uuid": "1a2b3c4d-0000-4000-8000-000000000000",
        "id": 3,
        "description": "Call the Bank about loan",
        "entry": T0,
        "modified": T0,
        "project": "home.garden",
        "tags": frozenset({"phone", "urgent"}),
        "priority": Priority.H,
    }
    fields.update(overrides)
    return Task(**fields)  # type: ignore[arg-type]


def test_empty_filter_matches_pending_only() -> None:
    assert Filter().matches(task())
    assert not Filter().matches(task(status=Status.COMPLETED, id=None))


def test_status() -> None:
    done = task(status=Status.COMPLETED, id=None)
    assert Filter(status=Status.COMPLETED).matches(done)
    assert not Filter(status=Status.COMPLETED).matches(task())
    assert Filter().effective_status is Status.PENDING


@pytest.mark.parametrize(
    ("where", "expected"),
    [
        (Filter(ids=frozenset({3})), True),
        (Filter(ids=frozenset({1, 2})), False),
        (Filter(uuid_prefixes=("1a2b3c4d",)), True),
        (Filter(uuid_prefixes=("1a2b3c4d0000",)), True),  # dashes ignored
        (Filter(uuid_prefixes=("ffffffff",)), False),
        # ids and uuid prefixes form one selection (OR).
        (Filter(ids=frozenset({9}), uuid_prefixes=("1a2b3c4d",)), True),
    ],
)
def test_selection(where: Filter, expected: bool) -> None:
    assert where.matches(task()) is expected


@pytest.mark.parametrize(
    ("where", "expected"),
    [
        (Filter(tags_in=frozenset({"phone"})), True),
        (Filter(tags_in=frozenset({"phone", "urgent"})), True),
        (Filter(tags_in=frozenset({"phone", "work"})), False),
        (Filter(tags_out=frozenset({"work"})), True),
        (Filter(tags_out=frozenset({"urgent"})), False),
    ],
)
def test_tags(where: Filter, expected: bool) -> None:
    assert where.matches(task()) is expected


@pytest.mark.parametrize(
    ("project", "task_project", "expected"),
    [
        ("home", "home", True),
        ("home", "home.garden", True),
        ("home.garden", "home.garden", True),
        ("home", "homework", False),
        ("home.garden", "home", False),
        ("home", None, False),
        (NONE, None, True),
        (NONE, "home", False),
    ],
)
def test_project(project: str, task_project: str | None, expected: bool) -> None:
    assert Filter(project=project).matches(task(project=task_project)) is expected


@pytest.mark.parametrize(
    ("priority", "task_priority", "expected"),
    [
        (Priority.H, Priority.H, True),
        (Priority.M, Priority.H, False),
        (Priority.H, None, False),
        (NONE, None, True),
        (NONE, Priority.L, False),
    ],
)
def test_priority(priority: Priority | str, task_priority: Priority | None, expected: bool) -> None:
    where = Filter(priority=priority)  # type: ignore[arg-type]
    assert where.matches(task(priority=task_priority)) is expected


@pytest.mark.parametrize(
    ("words", "expected"),
    [(("bank",), True), (("BANK", "loan"), True), (("bank", "car"), False), (("é",), False)],
)
def test_words_are_case_insensitive_substrings(words: tuple[str, ...], expected: bool) -> None:
    assert Filter(words=words).matches(task()) is expected


def test_words_unicode_casefold() -> None:
    assert Filter(words=("écrire",)).matches(task(description="ÉCRIRE le rapport"))


def test_all_criteria_and_combined() -> None:
    where = Filter(ids=frozenset({3}), tags_in=frozenset({"phone"}), project="home")
    assert where.matches(task())
    assert not where.matches(task(project="work"))


def test_due_before_and_after() -> None:
    due = task(due=T0)
    assert Filter(due_before=T0 + timedelta(seconds=1)).matches(due)
    assert not Filter(due_before=T0).matches(due)  # strict
    assert Filter(due_after=T0 - timedelta(seconds=1)).matches(due)
    assert not Filter(due_after=T0).matches(due)
    assert Filter(due_after=T0 - timedelta(days=1), due_before=T0 + timedelta(days=1)).matches(due)


def test_due_filters_exclude_tasks_without_due() -> None:
    assert not Filter(due_before=T0).matches(task())
    assert not Filter(due_after=T0).matches(task())
