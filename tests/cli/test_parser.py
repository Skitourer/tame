from datetime import UTC, datetime

import pytest

from tame.cli.parser import (
    AddArgs,
    ParsedCommand,
    match_command,
    parse_add,
    parse_command,
    parse_filter,
    parse_modify,
)
from tame.core.dates import parse_date
from tame.core.filters import ALL, Filter
from tame.core.models import NONE, Changes, Priority, Status
from tame.errors import UsageError, ValidationError

NOW = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)


def cmd(line: str) -> ParsedCommand:
    return parse_command(line.split())


# --- Rule 1: command detection ------------------------------------------------


@pytest.mark.parametrize(
    ("token", "name"),
    [("add", "add"), ("mod", "modify"), ("li", "list"), ("v", "version"), ("don", "done")],
)
def test_match_command_exact_or_unique_prefix(token: str, name: str) -> None:
    assert match_command(token) == name


@pytest.mark.parametrize("token", ["", "bank", "3", "+tag", "project:x", "lists"])
def test_match_command_none(token: str) -> None:
    assert match_command(token) is None


@pytest.mark.parametrize(("token", "candidates"), [("d", "delete, done"), ("i", "import, info")])
def test_match_command_ambiguous(token: str, candidates: str) -> None:
    with pytest.raises(UsageError) as exc:
        match_command(token)
    assert exc.value.key == "error.ambiguous_command"
    assert exc.value.params["candidates"] == candidates


def test_no_args_means_list() -> None:
    assert parse_command([]) == ParsedCommand("list")


def test_filter_without_command_means_list() -> None:
    assert cmd("project:home +phone") == ParsedCommand("list", filter=("project:home", "+phone"))


def test_double_dash_stops_command_search() -> None:
    assert cmd("-- list") == ParsedCommand("list", filter=("--", "list"))


# --- Spec examples (§4, §5) ---------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("project:home list", ParsedCommand("list", filter=("project:home",))),
        ("3,5 done", ParsedCommand("done", filter=("3,5",))),
        ("4 delete", ParsedCommand("delete", filter=("4",))),
        ("12 modify due:mon -phone", ParsedCommand("modify", ("12",), ("due:mon", "-phone"))),
        ("7 info", ParsedCommand("info", filter=("7",))),
        ("project:home export", ParsedCommand("export", filter=("project:home",))),
        ("import f.json", ParsedCommand("import", args=("f.json",))),
        ("alias install task", ParsedCommand("alias", args=("install", "task"))),
        ("help", ParsedCommand("help")),
        ("help add", ParsedCommand("help", args=("add",))),
        ("version", ParsedCommand("version")),
        ("undo", ParsedCommand("undo")),
        (
            "add Call bank project:home +phone due:tomorrow pri:H",
            ParsedCommand(
                "add", args=("Call", "bank", "project:home", "+phone", "due:tomorrow", "pri:H")
            ),
        ),
        ("add -- done the report", ParsedCommand("add", args=("--", "done", "the", "report"))),
    ],
)
def test_spec_examples(line: str, expected: ParsedCommand) -> None:
    assert cmd(line) == expected


# --- Rules 2-4: TW order vs classic order -------------------------------------


def test_rule3_add_never_takes_filter_after() -> None:
    assert cmd("add 3 +x done") == ParsedCommand("add", args=("3", "+x", "done"))


def test_rule3_add_rejects_filter_before() -> None:
    with pytest.raises(UsageError) as exc:
        cmd("project:x add foo")
    assert exc.value.key == "error.filter_not_allowed"


def test_rule4_classic_order_list() -> None:
    assert cmd("list project:home +phone") == ParsedCommand(
        "list", filter=("project:home", "+phone")
    )


def test_rule4_argless_command_trailing_words_join_filter() -> None:
    assert cmd("list +phone bank") == ParsedCommand("list", filter=("+phone", "bank"))
    assert cmd("bank list +phone") == ParsedCommand("list", filter=("bank", "+phone"))


def test_rule4_classic_done() -> None:
    assert cmd("done 3,5") == ParsedCommand("done", filter=("3,5",))


def test_rule4_classic_modify_only_ids_are_filter() -> None:
    assert cmd("modify 12 +x pri:H new text") == ParsedCommand(
        "modify", filter=("12",), args=("+x", "pri:H", "new", "text")
    )
    assert cmd("mod 1a2b3c4d due:mon") == ParsedCommand(
        "modify", filter=("1a2b3c4d",), args=("due:mon",)
    )


def test_rule2_tw_order_modify() -> None:
    assert cmd("+x modify pri:L") == ParsedCommand("modify", filter=("+x",), args=("pri:L",))


@pytest.mark.parametrize("line", ["3 version", "help +x", "+x undo", "3 import f.json"])
def test_filter_rejected_for_non_filter_commands(line: str) -> None:
    with pytest.raises(UsageError) as exc:
        cmd(line)
    assert exc.value.key == "error.filter_not_allowed"


# --- Filter tokens --------------------------------------------------------------


def test_parse_filter_empty() -> None:
    assert parse_filter([]) == Filter()


@pytest.mark.parametrize(
    ("token", "ids"),
    [("3", {3}), ("3,5", {3, 5}), ("2-6", {2, 3, 4, 5, 6}), ("1,4-5", {1, 4, 5}), ("7-7", {7})],
)
def test_parse_filter_ids(token: str, ids: set[int]) -> None:
    assert parse_filter([token]).ids == ids


def test_parse_filter_ids_accumulate() -> None:
    assert parse_filter(["3", "5"]).ids == {3, 5}


def test_parse_filter_bad_range() -> None:
    with pytest.raises(UsageError) as exc:
        parse_filter(["6-2"])
    assert exc.value.key == "error.invalid_id_range"


@pytest.mark.parametrize(
    ("token", "prefix"),
    [
        ("1a2b3c4d", "1a2b3c4d"),
        ("DEADBEEF00", "deadbeef00"),
        ("12345678-9abc", "123456789abc"),
        ("11111111-1111-4111-8111-111111111111", "11111111111141118111111111111111"),
    ],
)
def test_parse_filter_uuid_prefix(token: str, prefix: str) -> None:
    assert parse_filter([token]).uuid_prefixes == (prefix,)


def test_parse_filter_digits_only_is_id() -> None:
    assert parse_filter(["12345678"]) == Filter(ids=frozenset({12345678}))


def test_parse_filter_tags() -> None:
    f = parse_filter(["+a", "-b", "+c"])
    assert (f.tags_in, f.tags_out) == ({"a", "c"}, {"b"})


def test_parse_filter_attrs() -> None:
    f = parse_filter(["project:home.garden", "pri:h", "status:Completed"])
    assert (f.project, f.priority, f.status) == ("home.garden", Priority.H, Status.COMPLETED)


def test_parse_filter_empty_attr_means_none() -> None:
    f = parse_filter(["project:", "priority:"])
    assert (f.project, f.priority) == (NONE, NONE)


def test_parse_filter_words() -> None:
    assert parse_filter(["Call", "bank"]).words == ("Call", "bank")


def test_parse_filter_double_dash() -> None:
    assert parse_filter(["+a", "--", "+b", "3"]) == Filter(
        tags_in=frozenset({"a"}), words=("+b", "3")
    )


@pytest.mark.parametrize(
    ("token", "name"), [("foo:bar", "foo"), ("due.on:fri", "due.on"), ("due:x", "due")]
)
def test_parse_filter_unknown_attr(token: str, name: str) -> None:
    # due.before/after arrive with dates in roadmap step 5.
    with pytest.raises(UsageError) as exc:
        parse_filter([token])
    assert (exc.value.key, exc.value.params) == ("error.unknown_attribute", {"name": name})


@pytest.mark.parametrize(
    ("token", "key"),
    [
        ("status:waiting", "error.invalid_status"),
        ("status:", "error.invalid_status"),
        ("pri:Z", "error.invalid_priority"),
        ("project:a..b", "error.invalid_project"),
        ("+-x", "error.invalid_tag"),
    ],
)
def test_parse_filter_invalid_values(token: str, key: str) -> None:
    with pytest.raises(ValidationError) as exc:
        parse_filter([token])
    assert exc.value.key == key


# --- add ------------------------------------------------------------------------


def test_parse_add_spec_example() -> None:
    # SPEC §5: `tk add Call bank project:home +phone due:tomorrow pri:H`.
    tokens = ["Call", "bank", "project:home", "+phone", "due:tomorrow", "pri:H"]
    assert parse_add(tokens, NOW) == AddArgs(
        "Call bank",
        project="home",
        tags=("phone",),
        priority="H",
        due=parse_date("tomorrow", NOW),
    )


def test_parse_add_invalid_due() -> None:
    with pytest.raises(UsageError) as exc:
        parse_add(["x", "due:someday"])
    assert exc.value.key == "error.invalid_date"


def test_parse_add_mods_anywhere() -> None:
    tokens = ["+a", "Write", "priority:L", "report", "+b"]
    assert parse_add(tokens) == AddArgs("Write report", tags=("a", "b"), priority="L")


def test_parse_add_double_dash_ends_parsing() -> None:
    # SPEC §4 rule 5: `tk add -- done the report`.
    assert parse_add(["--", "done", "the", "report"]) == AddArgs("done the report")
    assert parse_add(["+x", "--", "+y", "pri:H"]) == AddArgs("+y pri:H", tags=("x",))


def test_parse_add_empty_attr_is_none() -> None:
    assert parse_add(["x", "project:home", "project:"]) == AddArgs("x")


def test_parse_add_unknown_attr() -> None:
    with pytest.raises(UsageError) as exc:
        parse_add(["x", "foo:bar"])
    assert exc.value.key == "error.unknown_attribute"
    assert exc.value.params == {"name": "foo"}


@pytest.mark.parametrize("word", ["+", "10:30", "Re:", "-x"])
def test_parse_add_plain_words(word: str) -> None:
    assert parse_add(["a", word]) == AddArgs(f"a {word}")


# --- --yes --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("4 delete --yes", ParsedCommand("delete", filter=("4",), yes=True)),
        ("--yes 4 delete", ParsedCommand("delete", filter=("4",), yes=True)),
        ("delete --yes 4", ParsedCommand("delete", filter=("4",), yes=True)),
        ("modify 1-5 --yes +x", ParsedCommand("modify", ("1-5",), ("+x",), yes=True)),
        ("3 modify -- --yes", ParsedCommand("modify", ("3",), ("--", "--yes"))),
        ("add -- --yes", ParsedCommand("add", args=("--", "--yes"))),
    ],
)
def test_yes_flag(line: str, expected: ParsedCommand) -> None:
    assert cmd(line) == expected


@pytest.mark.parametrize("line", ["list --yes", "version --yes", "3 info --yes"])
def test_yes_flag_rejected_for_commands_without_confirmation(line: str) -> None:
    with pytest.raises(UsageError) as exc:
        cmd(line)
    assert (exc.value.key, exc.value.params) == ("error.unexpected_argument", {"arg": "--yes"})


# --- Mods (modify) --------------------------------------------------------------


def test_parse_modify_spec_example() -> None:
    # SPEC §5: `tk 12 modify due:mon -phone`.
    assert parse_modify(["due:mon", "-phone"], NOW) == Changes(
        due=parse_date("mon", NOW), tags_remove=frozenset({"phone"})
    )


def test_parse_modify_clear_due() -> None:
    assert parse_modify(["due:"]) == Changes(due=NONE)


def test_parse_modify_all_mods() -> None:
    tokens = ["Call", "the", "bank", "+urgent", "project:work.q4", "-x", "priority:h"]
    assert parse_modify(tokens) == Changes(
        description="Call the bank",
        project="work.q4",
        priority=Priority.H,
        tags_add=frozenset({"urgent"}),
        tags_remove=frozenset({"x"}),
    )


def test_parse_modify_empty_attr_clears() -> None:
    assert parse_modify(["project:", "pri:"]) == Changes(project=NONE, priority=NONE)


def test_parse_modify_double_dash() -> None:
    assert parse_modify(["+a", "--", "-b", "pri:H"]) == Changes(
        description="-b pri:H", tags_add=frozenset({"a"})
    )


def test_parse_modify_nothing() -> None:
    assert parse_modify([]) == Changes()


@pytest.mark.parametrize(
    ("token", "key"),
    [
        ("due:someday", "error.invalid_date"),
        ("status:completed", "error.unknown_attribute"),
        ("pri:Z", "error.invalid_priority"),
        ("project:a..b", "error.invalid_project"),
        ("+-x", "error.invalid_tag"),
    ],
)
def test_parse_modify_errors(token: str, key: str) -> None:
    with pytest.raises(UsageError) as exc:
        parse_modify([token])
    assert exc.value.key == key


def test_parse_filter_due_spec_examples() -> None:
    # SPEC §4: `due.before:fri`, `due.after:today`.
    assert parse_filter(["due.before:fri", "due.after:today"], NOW) == Filter(
        due_before=parse_date("fri", NOW), due_after=parse_date("today", NOW)
    )


def test_parse_filter_invalid_due() -> None:
    with pytest.raises(ValidationError) as exc:
        parse_filter(["due.before:someday"])
    assert exc.value.key == "error.invalid_date"


# --- --help ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("--help", ParsedCommand("help")),
        ("mod --help", ParsedCommand("help", args=("modify",))),
        ("3 done --help", ParsedCommand("help", args=("done",))),
        ("+x --help list", ParsedCommand("help", args=("list",))),
        ("add -- --help", ParsedCommand("add", args=("--", "--help"))),
    ],
)
def test_help_flag(line: str, expected: ParsedCommand) -> None:
    assert cmd(line) == expected


def test_parse_filter_status_all() -> None:
    assert parse_filter(["status:all"]).status == ALL
    assert parse_filter(["status:ALL"]).status == ALL
