"""Filter operators and /patterns/ (SPEC §4 operators, since 0.4)."""

from datetime import UTC, datetime

import pytest

from tame.__main__ import main
from tame.cli.parser import parse_filter
from tame.core.filters import AllOf, AnyOf, Filter, Not
from tame.core.models import Status
from tame.errors import UsageError

Capture = pytest.CaptureFixture[str]
NOW = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)


def run(capsys: Capture, *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture
def tasks(capsys: Capture) -> None:
    """1 Call Ann +phone pri:H, 2 Mail Bob +mail, 3 Fix the door +home, 4 Order paint +home H."""
    for line in (
        ("Call", "Ann", "+phone", "pri:H"),
        ("Mail", "Bob", "+mail"),
        ("Fix", "the", "door", "+home"),
        ("Order", "paint", "+home", "pri:H"),
    ):
        assert run(capsys, "add", *line)[0] == 0


def shown(capsys: Capture, *filter_tokens: str) -> set[str]:
    """Descriptions listed by ``tk <filter> list`` (empty set when nothing matches)."""
    code, out, _ = run(capsys, *filter_tokens, "list")
    if code != 0:
        return set()
    names = ("Call Ann", "Mail Bob", "Fix the door", "Order paint")
    return {name for name in names if name in out}


# --- Parsing -------------------------------------------------------------------------


def test_plain_filter_stays_one_filter() -> None:
    where = parse_filter(["3", "5", "+home", "milk"], NOW)
    assert isinstance(where, Filter)
    assert (where.ids, where.tags_in, where.words) == ({3, 5}, {"home"}, ("milk",))


def test_quoted_words_without_parentheses_stay_one_word() -> None:
    where = parse_filter(["buy milk"], NOW)
    assert isinstance(where, Filter) and where.words == ("buy milk",)


def test_run_of_plain_tokens_is_one_term() -> None:
    where = parse_filter(["3", "5", "+home", "or", "+urgent"], NOW)
    assert isinstance(where, AnyOf)
    first, second = where.operands
    assert isinstance(first, Filter) and first.ids == {3, 5} and first.tags_in == {"home"}
    assert isinstance(second, Filter) and second.tags_in == {"urgent"}


def test_not_applies_to_the_next_token_only() -> None:
    where = parse_filter(["not", "+a", "+b"], NOW)
    assert isinstance(where, AllOf)
    negated, plain = where.operands
    assert isinstance(negated, Not) and isinstance(plain, Filter) and plain.tags_in == {"b"}


def test_and_binds_tighter_than_or() -> None:
    where = parse_filter(["+a", "or", "+b", "and", "+c"], NOW)
    assert isinstance(where, AnyOf) and isinstance(where.operands[1], AllOf)


def test_one_quoted_token_with_parentheses_is_split() -> None:
    where = parse_filter(["(+phone or +mail) and pri:H"], NOW)
    assert isinstance(where, AllOf) and isinstance(where.operands[0], AnyOf)
    assert parse_filter(["(+a", "or", "+b)"], NOW) == parse_filter(["(+a or +b)"], NOW)


def test_double_dash_words_join_the_expression() -> None:
    where = parse_filter(["+a", "or", "+b", "--", "or"], NOW)
    assert isinstance(where, AllOf)
    tail = where.operands[1]
    assert isinstance(tail, Filter) and tail.words == ("or",)


def test_pattern_token() -> None:
    where = parse_filter(["/^ca(ll|t)/"], NOW)
    assert isinstance(where, Filter) and where.patterns[0].pattern == "^ca(ll|t)"
    assert parse_filter(["//"], NOW) == Filter(words=("//",))


@pytest.mark.parametrize(
    ("tokens", "key"),
    [
        (["(+a or +b"], "error.filter_missing_paren"),
        (["+a)"], "error.filter_unexpected_paren"),
        (["(", ")"], "error.filter_empty_parens"),
        (["or", "+a"], "error.filter_operand"),
        (["+a", "or"], "error.filter_operand"),
        (["+a", "or", "or", "+b"], "error.filter_operand"),
        (["+a", "and"], "error.filter_operand"),
        (["and", "+a"], "error.filter_operand"),
        (["+a", "and", "and", "+b"], "error.filter_operand"),
        (["+a", "not"], "error.filter_not_operand"),
        (["not", "or", "+a"], "error.filter_not_operand"),
        (["/a(/"], "error.invalid_pattern"),
    ],
)
def test_malformed_expressions(tokens: list[str], key: str) -> None:
    with pytest.raises(UsageError) as exc:
        parse_filter(tokens, NOW)
    assert exc.value.key == key


def test_status_rule_is_global() -> None:
    assert parse_filter(["not", "+a"], NOW).statuses == (Status.PENDING,)
    assert parse_filter(["status:completed", "or", "+a"], NOW).statuses == tuple(Status)
    narrowed = AllOf((parse_filter(["status:completed"], NOW), Filter()))
    assert narrowed.statuses == (Status.COMPLETED,)


# --- Commands ------------------------------------------------------------------------


@pytest.mark.usefixtures("tasks")
def test_or_and_parentheses(capsys: Capture) -> None:
    assert shown(capsys, "+phone", "or", "+mail") == {"Call Ann", "Mail Bob"}
    assert shown(capsys, "(+phone or +home) and pri:H") == {"Call Ann", "Order paint"}
    assert shown(capsys, "(+phone or +home)", "pri:H") == {"Call Ann", "Order paint"}
    assert shown(capsys, "+phone", "or", "+home", "pri:H") == {"Call Ann", "Order paint"}


@pytest.mark.usefixtures("tasks")
def test_not(capsys: Capture) -> None:
    assert shown(capsys, "not", "+home") == {"Call Ann", "Mail Bob"}
    assert shown(capsys, "not", "(+home or +phone)") == {"Mail Bob"}
    assert shown(capsys, "not", "not", "+mail") == {"Mail Bob"}


@pytest.mark.usefixtures("tasks")
def test_ids_inside_an_expression(capsys: Capture) -> None:
    assert shown(capsys, "1", "2", "+phone", "or", "+home") == {
        "Call Ann",
        "Fix the door",
        "Order paint",
    }


@pytest.mark.usefixtures("tasks")
def test_pattern_on_description(capsys: Capture) -> None:
    assert shown(capsys, "/^(call|mail) /") == {"Call Ann", "Mail Bob"}
    assert shown(capsys, "/door$/") == {"Fix the door"}
    code, _, err = run(capsys, "/a[/", "list")
    assert code == 1 and "Invalid pattern /a[/" in err


@pytest.mark.usefixtures("tasks")
def test_filter_after_a_command_without_args(capsys: Capture) -> None:
    code, out, _ = run(capsys, "list", "+phone", "or", "+mail")
    assert code == 0 and "Call Ann" in out and "Mail Bob" in out and "Fix" not in out


@pytest.mark.usefixtures("tasks")
def test_status_in_an_or_is_a_plain_condition(capsys: Capture) -> None:
    run(capsys, "3", "done")
    run(capsys, "2", "done")
    code, out, _ = run(capsys, "status:completed", "or", "+home", "list")
    assert code == 0 and "Mail Bob" in out and "Fix the door" in out and "Order paint" in out
    assert "Call Ann" not in out
    assert shown(capsys, "not", "+phone") == {"Order paint"}  # pending only


@pytest.mark.usefixtures("tasks")
def test_write_commands_accept_an_expression(capsys: Capture) -> None:
    assert run(capsys, "+phone", "or", "+mail", "modify", "pri:L")[0] == 0
    code, out, _ = run(capsys, "pri:L", "list")
    assert code == 0 and "Call Ann" in out and "Mail Bob" in out and "Fix" not in out
    assert run(capsys, "not", "+home", "done")[0] == 0
    assert shown(capsys) == {"Fix the door", "Order paint"}


@pytest.mark.usefixtures("tasks")
def test_next_and_stop_narrow_an_expression(capsys: Capture) -> None:
    run(capsys, "add", "Paint walls", "+home", "depends:4")
    code, out, _ = run(capsys, "+home", "or", "+mail", "next")
    assert code == 0 and "Order paint" in out and "Paint walls" not in out
    run(capsys, "1", "start")
    assert run(capsys, "+mail", "or", "+home", "stop")[0] == 2  # none of them is active
    assert run(capsys, "+mail", "or", "+phone", "stop")[0] == 0


@pytest.mark.usefixtures("tasks")
def test_purge_takes_an_expression(capsys: Capture) -> None:
    run(capsys, "2", "3", "delete", "--yes")
    assert run(capsys, "+mail", "or", "+phone", "purge", "--yes")[0] == 0
    code, out, _ = run(capsys, "status:deleted", "list")
    assert code == 0 and "Fix the door" in out and "Mail Bob" not in out
    code, _, err = run(capsys, "+a", "or", "status:completed", "purge", "--yes")
    assert code == 1 and "status:" in err


@pytest.mark.usefixtures("tasks")
def test_malformed_filter_is_a_usage_error(capsys: Capture) -> None:
    code, _, err = run(capsys, "(+phone or +mail", "list")
    assert code == 1 and "Missing ')'" in err
    code, _, err = run(capsys, "+phone", "or", "list")
    assert code == 1 and "'or' needs a filter on each side." in err


@pytest.mark.usefixtures("tasks")
def test_reserved_words_can_still_be_searched(capsys: Capture) -> None:
    run(capsys, "add", "Black or white")
    code, out, _ = run(capsys, "/ or /", "list")
    assert code == 0 and "Black or white" in out
    code, out, _ = run(capsys, "list", "--", "or")
    assert code == 0 and "Black or white" in out
