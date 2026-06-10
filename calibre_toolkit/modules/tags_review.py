"""
MQG-05 per-book tag review — pure domain helpers.

HTML stripping and the per-book metadata panel builder. The tags-review
orchestration (search → AI assessment → prompt → write + lock) lives in
`commands/tags_review.py`.
"""

from __future__ import annotations

import re

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from ..db import Book

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    text = _HTML_TAG_RE.sub(" ", html)
    return " ".join(text.split())


def _book_panel(
    book: Book,
    tags: list[str],
    description: str,
    series: str,
    year: str,
    publisher: str,
    lcc_summary: str,
    progress: str,
) -> Panel:
    lines: list = []

    title_line = Text()
    title_line.append(book.title, style="bold white")
    lines.append(title_line)

    meta = Text()
    meta.append(book.authors_display, style="dim")
    if year:
        meta.append(f"  ·  {year}", style="dim")
    lines.append(meta)

    extras = []
    if series:
        extras.append(series)
    if publisher:
        extras.append(publisher)
    if extras:
        lines.append(Text("  ·  ".join(extras), style="dim"))

    lines.append(Text(""))

    tag_header = Text()
    tag_header.append(f"Current tags ({len(tags)}):", style="dim")
    lines.append(tag_header)
    lines.append(Text("  " + (", ".join(tags) if tags else "(none)"), style="cyan"))

    if description:
        lines.append(Text(""))
        lines.append(Text("Description:", style="dim"))
        truncated = description[:400]
        if len(description) > 400:
            truncated += "…"
        lines.append(Text("  " + truncated))

    if lcc_summary:
        lines.append(Text(""))
        lcc_line = Text()
        lcc_line.append("LCC: ", style="dim")
        lcc_line.append(lcc_summary, style="italic dim")
        lines.append(lcc_line)

    return Panel(
        Group(*lines),
        title=f"[dim]{progress}[/dim]",
        border_style="blue",
        padding=(0, 1),
    )
