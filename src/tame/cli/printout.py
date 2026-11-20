"""Printable task list (``tk print``): a self-contained HTML page, one section per project.

The page is plain HTML and CSS (A4, black and white, no external resources), so any
browser can print it or save it as PDF.
"""

from collections.abc import Sequence
from datetime import datetime
from html import escape
from itertools import groupby

from tame.cli.render import DEFAULT_DATE_FORMAT, due_state
from tame.core.models import Task
from tame.core.urgency import DEFAULT_COEFFICIENTS, Coefficients, by_urgency
from tame.i18n import current_language, t

BLANK_LINES = 3
"""Empty lines with a box at the end of the page, for tasks added by hand."""

_STYLE = """
@page { size: A4; margin: 15mm; }
* { box-sizing: border-box; }
body { font: 11pt/1.4 system-ui, "Segoe UI", Arial, sans-serif; color: #000; background: #fff;
  margin: 0 auto; max-width: 180mm; padding: 8mm 0; }
header { border-bottom: 2px solid #000; margin-bottom: 6mm; padding-bottom: 2mm; }
h1 { font-size: 18pt; margin: 0; }
.meta { color: #444; font-size: 9pt; }
h2 { font-size: 13pt; margin: 6mm 0 2mm; border-bottom: 1px solid #999; }
table { width: 100%; border-collapse: collapse; }
td { padding: 1.5mm 2mm; border-bottom: 1px solid #ddd; vertical-align: top; color: #000; }
td.box { width: 7mm; font-size: 14pt; line-height: 1; }
td.desc { width: 100%; }
td.due { white-space: nowrap; text-align: right; }
.pri { border: 1px solid #000; border-radius: 1mm; padding: 0 1mm; font-size: 8.5pt;
  font-weight: bold; color: #000; white-space: nowrap; }
.tags { color: #444; font-size: 9pt; }
.note { display: block; color: #444; font-size: 9pt; font-style: italic; }
.late { font-weight: bold; }
.blank td { height: 9mm; border-bottom: 1px dotted #999; }
.extra { margin-top: 8mm; }
.kind { margin-top: 8mm; font-style: italic; text-align: center; }
section { break-inside: avoid-page; }
tr { break-inside: avoid; }
footer { margin-top: 8mm; color: #666; font-size: 8pt; text-align: right; }
@media print { body { padding: 0; } }
"""


def print_page(
    tasks: Sequence[Task],
    now: datetime,
    *,
    filter_text: str = "",
    coefficients: Coefficients = DEFAULT_COEFFICIENTS,
    date_format: str = DEFAULT_DATE_FORMAT,
    auto_print: bool = False,
    kind_word: str | None = None,
) -> str:
    """Return a printable HTML page of ``tasks``, grouped by project.

    Projects are sorted by name, tasks without a project last; within a project, tasks
    are sorted pending first, then by urgency.

    Args:
        tasks: Tasks to print.
        now: Current time, for the date in the title and due highlighting.
        filter_text: The filter as typed, shown in the title ("" for none).
        coefficients: Urgency weights.
        date_format: strftime format of dates.
        auto_print: Open the browser's print dialog when the page loads.
        kind_word: A kind word for the foot of the page, if any.
    """

    def project_key(task: Task) -> tuple[bool, str]:
        return task.project is None, (task.project or "").casefold()

    sections = []
    for project, group in groupby(sorted(tasks, key=project_key), key=lambda task: task.project):
        title = escape(project) if project else escape(t("print.no_project"))
        rows = "\n".join(
            _row(task, now, date_format) for task in by_urgency(list(group), now, coefficients)
        )
        sections.append(f"<section>\n<h2>{title}</h2>\n<table>\n{rows}\n</table>\n</section>")

    count = t("print.count_one") if len(tasks) == 1 else t("print.count", count=len(tasks))
    printed = now.astimezone().strftime(f"{date_format} %H:%M")
    meta = escape(printed) + " · " + escape(count)
    title = t("print.title_filtered", filter=filter_text) if filter_text else t("print.title")
    blank = '<tr class="blank"><td class="box">&#9744;</td><td colspan="2"></td></tr>'
    extra = f'<table class="extra">\n{chr(10).join([blank] * BLANK_LINES)}\n</table>'
    script = (
        "<script>window.addEventListener('load', () => window.print());</script>"
        if auto_print
        else ""
    )
    return f"""<!doctype html>
<html lang="{current_language()}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{_STYLE}</style>
</head>
<body>
<header>
<h1>{escape(title)}</h1>
<div class="meta">{meta}</div>
</header>
{chr(10).join(sections)}
{extra}
{f'<p class="kind">{escape(kind_word)}</p>' if kind_word else ""}
<footer>{escape(t("print.footer"))}</footer>
{script}
</body>
</html>
"""


def _row(task: Task, now: datetime, date_format: str) -> str:
    box = "&#9745;" if task.end is not None else "&#9744;"
    priority = f' <span class="pri">!{task.priority.value}</span>' if task.priority else ""
    tags = " ".join(f"+{escape(tag)}" for tag in sorted(task.tags))
    tags_html = f' <span class="tags">{tags}</span>' if tags else ""
    notes = "".join(
        f'<span class="note">{escape(note.entry.astimezone().strftime(date_format))} '
        f"{escape(note.description)}</span>"
        for note in task.annotations
    )
    return (
        f'<tr><td class="box">{box}</td>'
        f'<td class="desc">{escape(task.description)}{priority}{tags_html}{notes}</td>'
        f"{_due_cell(task, now, date_format)}</tr>"
    )


def _due_cell(task: Task, now: datetime, date_format: str) -> str:
    """Return the due date cell: ``due <date>``, plus ``today`` or, in bold, ``late``."""
    if task.due is None:
        return '<td class="due"></td>'
    text = t("print.due", date=task.due.astimezone().strftime(date_format))
    match due_state(task, now) if task.end is None else None:
        case "overdue":
            return f'<td class="due late">{escape(text)} · {escape(t("print.late"))}</td>'
        case "today":
            return f'<td class="due">{escape(text)} · {escape(t("print.today"))}</td>'
        case _:
            return f'<td class="due">{escape(text)}</td>'
