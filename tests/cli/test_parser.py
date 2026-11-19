import pytest

from tame.cli.parser import AddArgs, ParsedCommand, parse_add, parse_command, resolve_command
from tame.errors import UsageError


def test_no_args_means_list() -> None:
    assert parse_command([]) == ParsedCommand("list")


def test_command_and_args() -> None:
    assert parse_command(["add", "a", "b"]) == ParsedCommand("add", ("a", "b"))


@pytest.mark.parametrize(
    ("token", "name"), [("add", "add"), ("a", "add"), ("li", "list"), ("v", "version")]
)
def test_resolve_command_exact_or_prefix(token: str, name: str) -> None:
    assert resolve_command(token) == name


@pytest.mark.parametrize("token", ["", "frobnicate", "3", "+tag"])
def test_resolve_command_unknown(token: str) -> None:
    with pytest.raises(UsageError) as exc:
        resolve_command(token)
    assert exc.value.key == "error.unknown_command"


def test_resolve_command_ambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tame.cli.parser.COMMANDS", ("done", "delete"))
    with pytest.raises(UsageError) as exc:
        resolve_command("d")
    assert exc.value.key == "error.ambiguous_command"
    assert exc.value.params["candidates"] == "done, delete"


def test_parse_add_spec_example() -> None:
    # SPEC §5 example without due: (dates arrive in step 5).
    tokens = ["Call", "bank", "project:home", "+phone", "pri:H"]
    assert parse_add(tokens) == AddArgs("Call bank", project="home", tags=("phone",), priority="H")


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
