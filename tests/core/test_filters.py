from datetime import UTC, datetime, timedelta, timezone

import pytest

from tame.core.filters import ALL, Filter, VirtualTagger
from tame.core.models import NONE, Annotation, Priority, Status, Task

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
    assert Filter().statuses == (Status.PENDING,)
    assert Filter(status=ALL).statuses == tuple(Status)
    assert Filter(status=ALL).matches(done)
    assert Filter(status=ALL).matches(task())


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


# --- Virtual tags (SPEC §4) -------------------------------------------------------------

TZ = timezone(timedelta(hours=1))
NOW = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)  # Thursday 10:30 local
OTHER = "2a2b3c4d-0000-4000-8000-000000000000"
DATE_TAGS = {"OVERDUE", "TODAY", "TOMORROW", "WEEK", "MONTH", "DUE"}


def local(*args: int) -> datetime:
    return datetime(*args, tzinfo=TZ).astimezone(UTC)  # type: ignore[misc]


def tagger(pending: frozenset[str] = frozenset()) -> VirtualTagger:
    return VirtualTagger(NOW, pending, TZ)


@pytest.mark.parametrize(
    ("due", "expected"),
    [
        (local(2026, 11, 19, 8), {"OVERDUE", "TODAY", "WEEK", "MONTH"}),
        (local(2026, 11, 19, 23, 59), {"TODAY", "WEEK", "MONTH", "DUE"}),
        (local(2026, 11, 20), {"TOMORROW", "WEEK", "MONTH", "DUE"}),
        (local(2026, 11, 16), {"OVERDUE", "WEEK", "MONTH"}),
        (local(2026, 11, 15, 23, 59), {"OVERDUE", "MONTH"}),
        (local(2026, 11, 23), {"MONTH", "DUE"}),
        (local(2026, 11, 26, 10, 29), {"MONTH", "DUE"}),
        (local(2026, 11, 26, 10, 30), {"MONTH"}),
        (local(2026, 12, 1), set()),
        (local(2026, 10, 31), {"OVERDUE"}),
        (None, set()),
    ],
)
def test_virtual_date_tags(due: datetime | None, expected: set[str]) -> None:
    assert tagger()(task(due=due)) & DATE_TAGS == expected


def test_virtual_tags_of_plain_and_rich_tasks() -> None:
    plain = task(project=None, tags=frozenset())
    assert tagger()(plain) == {"UNBLOCKED"}
    rich = task(annotations=(Annotation(T0, "note"),))
    assert tagger()(rich) == {"ANNOTATED", "PROJECT", "TAGGED", "UNBLOCKED"}


def test_blocked_only_by_pending_dependencies() -> None:
    blocked = task(depends=frozenset({OTHER, "gone"}))
    assert "BLOCKED" in tagger(frozenset({OTHER}))(blocked)
    assert "UNBLOCKED" in tagger(frozenset())(blocked)


def test_closed_tasks_have_no_status_dependent_tags() -> None:
    done = task(
        status=Status.COMPLETED, id=None, due=local(2026, 11, 1), depends=frozenset({OTHER})
    )
    assert tagger(frozenset({OTHER}))(done) == {"PROJECT", "TAGGED"}


def test_filter_on_virtual_tags() -> None:
    where = Filter(virtual_in=frozenset({"TAGGED"}), virtual_out=frozenset({"OVERDUE"}))
    assert where.uses_virtual_tags
    assert not Filter().uses_virtual_tags
    assert where.matches(task(), frozenset({"TAGGED"}))
    assert not where.matches(task(), frozenset({"TAGGED", "OVERDUE"}))
    assert not where.matches(task(), frozenset())


def test_waiting_tag_and_shows_waiting() -> None:
    waiting = task(wait=NOW + timedelta(hours=1))
    assert "WAITING" in tagger()(waiting)
    assert "WAITING" not in tagger()(task(wait=NOW))
    assert "WAITING" not in tagger()(task(wait=NOW + timedelta(1), status=Status.COMPLETED))
    assert not Filter().shows_waiting
    assert Filter(ids=frozenset({3})).shows_waiting
    assert Filter(uuid_prefixes=("1a2b3c4d",)).shows_waiting
    assert Filter(virtual_in=frozenset({"WAITING"})).shows_waiting
    assert Filter(status=ALL).shows_waiting
