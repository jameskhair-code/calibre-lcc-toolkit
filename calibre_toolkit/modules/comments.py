"""
MQG-04 Comments Enrichment — pure domain helpers.

Section labels, confidence/score styling, and the review-table builder.
The comments-enrich orchestration (read details → AI generate → review →
confirm → write) lives in `commands/comments_enrich.py`.
"""

from __future__ import annotations

import re

from rich.table import Table
from rich.text import Text
from rich import box

from ..ai import CommentsSuggestion


def _word_count(suggestions: list[CommentsSuggestion]) -> int:
    total = 0
    for s in suggestions:
        text = re.sub(r"<[^>]+>", " ", s.html or "")
        total += len(text.split())
    return total

_CONF_DISPLAY = {
    "high":   ("●", "green"),
    "medium": ("◐", "yellow"),
    "low":    ("○", "red"),
}

# Section keys + display labels, in render order. The fiction/non-fiction
# split is implicit — the AI returns empty strings for the inapplicable keys
# and the renderer skips them.
_SECTION_LABELS = [
    ("the_book",                     "The Book"),
    ("the_story",                    "The Story"),
    ("the_argument",                 "The Argument"),
    ("what_its_really_about",        "What It's Really About"),
    ("something_you_might_not_know", "Something You Might Not Know"),
    ("why_read_it",                  "Why Read It"),
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _truncate(text: str, max_chars: int = 130) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def _score_style(score: int) -> str:
    if score < 0:
        return "dim"
    if score >= 9:
        return "bold magenta"
    if score >= 7:
        return "bold green"
    if score >= 4:
        return "yellow"
    return "red"


def _build_review_table(suggestions: list[CommentsSuggestion]) -> Table:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
                  expand=True, show_lines=True)
    table.add_column("#",       style="dim", width=4, no_wrap=True)
    table.add_column("Conf",    width=5, no_wrap=True)
    table.add_column("Score",   width=7, no_wrap=True)
    table.add_column("Book",    ratio=2)
    table.add_column("Preview", ratio=6)

    for i, s in enumerate(suggestions, 1):
        icon, style = _CONF_DISPLAY.get(s.confidence, ("—", "dim"))

        score_text = Text()
        if s.must_read_score >= 0:
            score_text.append(f"{s.must_read_score}/10", style=_score_style(s.must_read_score))
        else:
            score_text.append("—", style="dim")

        book_text = Text()
        book_text.append(s.title)
        book_text.append(f"\n{s.authors_display}", style="dim")
        if s.book_type:
            book_text.append(f"\n[{s.book_type}]", style="dim italic")

        # Lead with whichever Section 1 key the AI populated (book_type-aware
        # without needing to branch on it).
        lead_key = "the_book" if (s.sections.get("the_book") or "").strip() else "the_story"
        preview = Text()
        for key, label in [
            (lead_key,      "Open"),
            ("why_read_it", "Sell"),
        ]:
            val = _truncate(s.sections.get(key, "") or "", 120)
            preview.append(f"{label}: ", style="dim")
            preview.append(val or "(empty)")
            preview.append("\n")
        if s.notes:
            preview.append(f"↳ {s.notes}", style="dim italic")
        # Surface HTML validation warnings inline in the table so a
        # reviewer flipping through tiers sees them without drilling in.
        if s.html_warnings:
            preview.append(f"\n[!] HTML: {s.html_warnings[0]}", style="bold red")
            extra = len(s.html_warnings) - 1
            if extra > 0:
                preview.append(f" (+{extra} more)", style="red")
        # Cross-step coherence warnings (item 16). Same surfacing pattern
        # as html_warnings — visible at the table tier so reviewers can
        # spot prose/tags drift without opening each book.
        if s.coherence_warnings:
            preview.append(
                f"\n[!] Coherence: {s.coherence_warnings[0]}",
                style="bold red",
            )
            extra = len(s.coherence_warnings) - 1
            if extra > 0:
                preview.append(f" (+{extra} more)", style="red")

        table.add_row(str(i), Text(icon, style=style), score_text, book_text, preview)

    return table
