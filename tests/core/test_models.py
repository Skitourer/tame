import pytest

from tame.core.models import (
    Priority,
    check_description,
    check_project,
    check_tag,
    parse_priority,
)
from tame.errors import ValidationError


def test_check_description_strips() -> None:
    assert check_description("  Call bank ") == "Call bank"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_check_description_rejects_blank(value: str) -> None:
    with pytest.raises(ValidationError) as exc:
        check_description(value)
    assert exc.value.key == "error.empty_description"


@pytest.mark.parametrize("tag", ["phone", "é", "a-b", "x+"])
def test_check_tag_accepts(tag: str) -> None:
    assert check_tag(tag) == tag


@pytest.mark.parametrize("tag", ["", "+phone", "-phone", "two words"])
def test_check_tag_rejects(tag: str) -> None:
    with pytest.raises(ValidationError) as exc:
        check_tag(tag)
    assert exc.value.params == {"tag": tag}


@pytest.mark.parametrize("project", ["home", "a.b", "work.client.x"])
def test_check_project_accepts(project: str) -> None:
    assert check_project(project) == project


@pytest.mark.parametrize("project", ["", ".a", "a.", "a..b", "my home"])
def test_check_project_rejects(project: str) -> None:
    with pytest.raises(ValidationError):
        check_project(project)


@pytest.mark.parametrize(("value", "expected"), [("H", Priority.H), ("m", Priority.M)])
def test_parse_priority(value: str, expected: Priority) -> None:
    assert parse_priority(value) is expected


@pytest.mark.parametrize("value", ["", "X", "high"])
def test_parse_priority_rejects(value: str) -> None:
    with pytest.raises(ValidationError) as exc:
        parse_priority(value)
    assert exc.value.key == "error.invalid_priority"
