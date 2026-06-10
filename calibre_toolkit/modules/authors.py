"""
Author/Title cleanup — pure domain helpers.

Diff rendering, the author-removal confidence gate, and the review-table
builder. The clean-titles orchestration (search → AI → review → apply)
lives in `commands/clean_titles.py`.
"""

from __future__ import annotations

from rich.table import Table
from rich.text import Text
from rich import box

from ..ai import CleanupSuggestion


def _confidence_style(confidence: str) -> tuple[str, str]:
    return {
        "high":   ("●", "green"),
        "medium": ("◑", "yellow"),
        "low":    ("○", "red"),
    }.get(confidence, ("?", "dim"))


def _diff_text(original: str, suggested: str) -> Text:
    if original == suggested:
        return Text(original, style="dim")
    t = Text()
    t.append(original, style="red strike")
    t.append("  →  ", style="dim")
    t.append(suggested, style="green bold")
    return t


def _gate_author_removals(suggestions: list[CleanupSuggestion]) -> int:
    """Cap any author-removal suggestion to low confidence (review-only).

    Author deletions from model memory are the one clean-titles change class
    that can silently corrupt data (the 2026-05-28 "J R" run dropped a real
    co-author at medium confidence and it auto-applied under "all"). Capping
    removals to low drops them out of every auto-apply path — high-only,
    --auto-apply-high, and the bulk "all" branch — and flags them red in the
    review table. Legitimate fixes (capitalisation, diacritics, ordering) are
    not removals and pass through untouched. Returns the count capped.
    """
    n = 0
    for s in suggestions:
        if s.removes_author and s.confidence != "low":
            s.confidence = "low"
            n += 1
    return n


def _build_review_table(suggestions: list[CleanupSuggestion]) -> Table:
    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4, no_wrap=True)
    table.add_column("Conf", width=5, no_wrap=True)
    table.add_column("Title", ratio=4)
    table.add_column("Authors", ratio=3)
    table.add_column("Notes", ratio=2, style="dim")

    for i, s in enumerate(suggestions, 1):
        icon, style = _confidence_style(s.confidence)
        conf_text = Text(icon, style=style)
        title_cell = _diff_text(s.original_title, s.suggested_title)
        author_cell = _diff_text(s.original_authors_display, s.suggested_authors_display)
        notes_cell = Text()
        if s.removes_author:
            notes_cell.append("removes author — review  ", style="bold red")
        notes_cell.append(s.notes or "", style="dim")
        table.add_row(str(i), conf_text, title_cell, author_cell, notes_cell)
    return table
