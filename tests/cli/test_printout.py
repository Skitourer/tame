from datetime import UTC, datetime, timedelta

import pytest

from tame.cli.parser import parse_command
from tame.cli.printout import print_page
from tame.core.models import Priority, Status, Task
from tame.errors import UsageError
from tame.i18n import set_language

NOW = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)


def make_task(description: str, **fields: object) -> Task:
    values: dict[str, object] = {"entry": NOW, "modified": NOW, **fields}
    return Task(uuid=description, description=description, **values)  # type: ignore[arg-type]


# --- Parser ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "filter_tokens", "args"),
    [
        (["print"], (), ()),
        (["+x", "print", "--file", "a.html"], ("+x",), ("--file", "a.html")),
        (["print", "+x", "--file", "a b.html", "bank"], ("+x", "bank"), ("--file", "a b.html")),
        (["print", "project:home", "due.before:eow"], ("project:home", "due.before:eow"), ()),
        (["p"], (), ()),
    ],
)
def test_parse_print(
    argv: list[str], filter_tokens: tuple[str, ...], args: tuple[str, ...]
) -> None:
    command = parse_command(argv)
    assert (command.name, command.filter, command.args) == ("print", filter_tokens, args)


def test_parse_print_file_needs_a_path() -> None:
    with pytest.raises(UsageError) as exc:
        parse_command(["print", "--file"])
    assert exc.value.key == "error.print_usage"


# --- Page ------------------------------------------------------------------------------


def test_sections_by_project_no_project_last() -> None:
    tasks = [
        make_task("loose"),
        make_task("weed", project="home.garden"),
        make_task("milk", project="Errands"),
        make_task("bills", project="home"),
    ]
    page = print_page(tasks, NOW)
    headings = [line[4:-5] for line in page.splitlines() if line.startswith("<h2>")]
    assert headings == ["Errands", "home", "home.garden", "No project"]


def test_tasks_sorted_by_urgency_within_a_project() -> None:
    tasks = [
        make_task("low", project="p"),
        make_task("high", project="p", priority=Priority.H),
    ]
    page = print_page(tasks, NOW)
    assert page.index("high") < page.index("low")


def test_row_content_and_escaping() -> None:
    task = make_task(
        "Call <bank> & co",
        tags=frozenset({"phone", "a&b"}),
        priority=Priority.H,
        due=NOW - timedelta(days=2),
    )
    page = print_page([task], NOW, date_format="%d/%m/%Y")
    assert 'Call &lt;bank&gt; &amp; co <span class="pri">!H</span>' in page
    assert '<span class="tags">+a&amp;b +phone</span>' in page
    assert '<td class="due late">due 17/11/2026 · late</td>' in page
    assert "&#9744;" in page  # empty box
    assert "<script" not in page


def test_due_today_and_later() -> None:
    today = make_task("today", due=NOW.replace(hour=0, minute=0))
    later = make_task("later", due=NOW + timedelta(days=3))
    page = print_page([today, later], NOW)
    assert '<td class="due">due 2026-11-19 · today</td>' in page
    assert '<td class="due">due 2026-11-22</td>' in page


def test_blank_lines_for_handwritten_tasks() -> None:
    page = print_page([make_task("a")], NOW)
    assert page.count('<tr class="blank">') == 3


def test_completed_tasks_are_ticked() -> None:
    task = make_task("done", status=Status.COMPLETED, end=NOW)
    assert "&#9745;" in print_page([task], NOW)


def test_title_count_filter_and_auto_print() -> None:
    page = print_page([make_task("a"), make_task("b")], NOW, filter_text="+x <y>", auto_print=True)
    assert "<title>Tasks: +x &lt;y&gt;</title>" in page
    assert "<h1>Tasks: +x &lt;y&gt;</h1>" in page
    assert "2 tasks" in page
    assert "window.print()" in page
    plain = print_page([make_task("a")], NOW)
    assert "<h1>Tasks</h1>" in plain
    assert "1 task" in plain
    local = NOW.astimezone().strftime("%Y-%m-%d %H:%M")
    assert f'<div class="meta">{local} · 1 task</div>' in plain


def test_page_follows_the_interface_language() -> None:
    set_language("fr")
    page = print_page([make_task("a")], NOW)
    assert '<html lang="fr">' in page
    assert "<title>Tâches</title>" in page
    assert "Sans projet" in page
    late = make_task("b", due=NOW - timedelta(days=1))
    assert "échéance 2026-11-18 · en retard" in print_page([late], NOW)


def test_print_shows_annotations_under_the_task() -> None:
    from tame.core.models import Annotation

    task = make_task("Call bank", annotations=(Annotation(NOW, "ask <Ann>"),))
    page = print_page([task], NOW, date_format="%Y-%m-%d")
    assert '<span class="note">2026-11-19 ask &lt;Ann&gt;</span>' in page
