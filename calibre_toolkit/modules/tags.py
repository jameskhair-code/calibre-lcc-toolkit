"""
MQG-05 Tags Enrichment — pure domain helpers.

The comments-excerpt builder, the review-table/diff renderers, and the
tags-cleanup grouping/scoping helpers. The tags-enrich orchestration lives
in `commands/tags_enrich.py`; the tags-cleanup orchestration lives in
`commands/tags_cleanup.py`.
"""

from __future__ import annotations

from rich.table import Table
from rich.text import Text
from rich import box

from ..ai import TagsSuggestion, TagOperation


# Cap for the comments excerpt fed into the tags prompt. ~400 chars
# is enough to surface period/geography mentions without bloating
# the user message — the AI does not need the full prose, just the
# coherence signal.
_COMMENTS_EXCERPT_MAX_CHARS = 400

_CONF_DISPLAY = {
    "high":   ("●", "green"),
    "medium": ("◐", "yellow"),
    "low":    ("○", "red"),
}


def _excerpt_from_comments(html_text: str) -> str:
    """Strip HTML and trim a book's existing comments to a short excerpt.

    Used as a coherence signal for the tags prompt and the coherence
    checker (item 16). Returns an empty string when the source is
    empty — callers treat empty as "no signal."
    """
    if not html_text:
        return ""
    import re
    plain = re.sub(r"<[^>]+>", " ", html_text)
    # Collapse runs of whitespace so the excerpt is dense.
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) <= _COMMENTS_EXCERPT_MAX_CHARS:
        return plain
    return plain[:_COMMENTS_EXCERPT_MAX_CHARS].rstrip() + "…"


def _build_review_table(suggestions: list[TagsSuggestion]) -> Table:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
                  expand=True, show_lines=True)
    table.add_column("#",       style="dim", width=4, no_wrap=True)
    table.add_column("Conf",    width=5, no_wrap=True)
    table.add_column("Book",    ratio=2)
    table.add_column("Tags",    ratio=5)

    for i, s in enumerate(suggestions, 1):
        icon, style = _CONF_DISPLAY.get(s.confidence, ("—", "dim"))

        book_text = Text()
        book_text.append(s.title)
        book_text.append(f"\n{s.authors_display}", style="dim")

        tags_text = _format_tags_diff(s)

        table.add_row(str(i), Text(icon, style=style), book_text, tags_text)

    return table


def _format_tags_diff(s: TagsSuggestion) -> Text:
    """Render kept/added/removed tags with colour coding in a single cell."""
    t = Text()
    kept_lower = {x.lower() for x in s.kept}
    removed_lower = {x.lower() for x in s.removed}

    parts: list[tuple[str, str]] = []

    # Kept tags — dim (already had them, no change)
    for tag in s.kept:
        parts.append((tag, "dim"))

    # Added tags — bold green (new)
    for tag in s.added:
        parts.append((f"+ {tag}", "bold green"))

    # Removed tags — red (being dropped)
    for tag in s.removed:
        parts.append((f"- {tag}", "red"))

    for idx, (label, color) in enumerate(parts):
        t.append(label, style=color)
        if idx < len(parts) - 1:
            t.append("  ", style="dim")

    if s.notes:
        t.append(f"\n↳ {s.notes}", style="dim italic")

    if not parts:
        t.append("(no change)", style="dim")

    # Coherence warnings (item 16). Surface inline so a reviewer flipping
    # through tiers sees them without drilling in.
    if s.coherence_warnings:
        t.append(f"\n[!] {s.coherence_warnings[0]}", style="bold red")
        extra = len(s.coherence_warnings) - 1
        if extra > 0:
            t.append(f" (+{extra} more)", style="red")

    return t


def _op_touches_scope(op: TagOperation, scope_tags: set[str]) -> bool:
    """True when at least one of the op's source tags is held by an in-scope book.

    Used by the `tags-cleanup --search` scope filter. Comparison is
    case-sensitive — tag names in Calibre's tags table are stored
    case-sensitively and the scanner/AI ops preserve that casing, so
    a case-insensitive compare would over-match (e.g. lowercase
    'fiction' surviving when only 'Fiction' is on a scope book).
    """
    return any(src in scope_tags for src in op.source_tags)


def _group_ops(ops: list[TagOperation]) -> dict[str, list[TagOperation]]:
    """Group operations by pattern_group, preserving a sensible display order."""
    order = [
        "formatting",
        "garbage",
        "bisac-code",
        "calibre-taxonomy",
        "date-range-lookup",
        "lcsh-bare-date-range",
        "lcsh-date-subject",
        "lcsh-chain",
        "ai-semantic",
    ]
    grouped: dict[str, list[TagOperation]] = {}
    for op in ops:
        grouped.setdefault(op.pattern_group, []).append(op)
    # Sort: known groups in defined order, unknown groups last alphabetically
    result: dict[str, list[TagOperation]] = {}
    for key in order:
        if key in grouped:
            result[key] = grouped.pop(key)
    for key in sorted(grouped):
        result[key] = grouped[key]
    return result


def _is_safe_group(group_key: str) -> bool:
    """Pattern groups that default to 'apply all' rather than review."""
    return group_key in {
        "formatting",
        "garbage",
        "bisac-code",
        "calibre-taxonomy",
        "date-range-lookup",
        "lcsh-bare-date-range",
        "lcsh-date-subject",
        "lcsh-chain",
    }
