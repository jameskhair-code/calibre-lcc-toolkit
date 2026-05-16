"""
MQG-05 per-book tag review with AI assessment and per-book locking.

For each unreviewed book:
  1. Display full metadata panel (title, authors, description, current tags, LCC)
  2. Ask the AI to assess completeness and propose improvements
  3. Show the AI diff to the user
  4. User chooses: approve AI / keep as-is / edit inline / skip / quit
  5. On approve/keep/edit: write tags (if changed) and set #tags_reviewed = yes
"""

from __future__ import annotations

import re
from typing import Optional

import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt

from ..ai import AIClient, TagsReviewSuggestion
from ..db import CalibreDB, Book

console = Console()

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


def _show_assessment(s: TagsReviewSuggestion) -> None:
    assessment_style = {
        "complete": "green",
        "needs_additions": "yellow",
        "needs_corrections": "red",
    }.get(s.assessment, "white")
    assessment_label = {
        "complete": "Complete ✓",
        "needs_additions": "Needs additions",
        "needs_corrections": "Needs corrections",
    }.get(s.assessment, s.assessment)

    header = Text()
    header.append("\nAI Assessment: ", style="dim")
    header.append(assessment_label, style=assessment_style)
    header.append(f"  [{s.confidence} confidence]", style="dim")
    console.print(header)

    if s.kept:
        console.print(Text("  Keep:    " + ", ".join(s.kept), style="dim"))
    if s.added:
        console.print(Text("  + Add:    " + ", ".join(s.added), style="bold green"))
    if s.removed:
        console.print(Text("  - Remove: " + ", ".join(s.removed), style="red"))
    if s.notes:
        console.print(Text(f"  ↳ {s.notes}", style="dim italic"))


def _prompt_action(has_ai: bool) -> str:
    """Return one of: 'A' approve-all, 'a' approve-AI, 'k' keep, 'e' edit, 's' skip, 'q' quit."""
    parts = []
    if has_ai:
        parts.append("[a]pprove AI")
        parts.append("[A]ll remaining")
    parts += ["[k]eep as-is", "[e]dit", "[s]kip", "[q]uit"]
    # Use Text so Rich doesn't interpret [a], [k], etc. as markup tags
    console.print(Text("\n  " + "   ".join(parts)))
    valid = (["a", "A"] if has_ai else []) + ["k", "e", "s", "q"]
    default = "a" if has_ai else "k"
    while True:
        raw = Prompt.ask("  Action", default=default, show_choices=False, show_default=True)
        c = raw.strip()[:1]
        if c in valid:
            return c
        console.print(f"  [red]Please enter one of: {', '.join(valid)}[/red]")


def _inline_edit(current: list[str], suggested: list[str] | None) -> list[str]:
    prefill = ", ".join(suggested if suggested is not None else current)
    console.print("\n  [dim]Edit tags (comma-separated):[/dim]")
    raw = Prompt.ask("  Tags", default=prefill)
    return [t.strip() for t in raw.split(",") if t.strip()]


def run_tags_review(
    db: CalibreDB,
    ai: Optional[AIClient],
    search_query: str,
    reviewed_column: str,
    lcc_summary_column: str | None = None,
    lcc_primary_column: str | None = None,
    lcc_secondary_column: str | None = None,
    limit: int | None = None,
    no_ai: bool = False,
    auto_approve_complete: bool = False,
) -> None:
    """Interactive per-book tag review with optional AI assessment and locking."""

    # ── 1. Search ─────────────────────────────────────────────────────────────
    try:
        with console.status(f"[cyan]Searching: {search_query}"):
            books = db.search(search_query)
    except RuntimeError as e:
        console.print(Panel(str(e), title="[red]Cannot access library[/red]", border_style="red"))
        raise typer.Exit(1)

    if not books:
        console.print("[yellow]No books matched — nothing to review.[/yellow]")
        raise typer.Exit()

    # ── 2. Load metadata + sort by tag count ascending ────────────────────────
    book_ids = [b.id for b in books]
    with console.status("[cyan]Loading metadata…"):
        tags_map      = db.get_tags_batch(book_ids)
        details_map   = db.get_book_details_batch(book_ids)
        lcc_summary_map  = db.get_custom_column_batch(book_ids, lcc_summary_column)  if lcc_summary_column  else {}
        lcc_primary_map  = db.get_custom_column_batch(book_ids, lcc_primary_column)  if lcc_primary_column  else {}
        lcc_secondary_map = db.get_custom_column_batch(book_ids, lcc_secondary_column) if lcc_secondary_column else {}

    books_sorted = sorted(books, key=lambda b: len(tags_map.get(b.id, [])))
    if limit:
        books_sorted = books_sorted[:limit]

    total = len(books_sorted)
    shown = len(books)
    cap_note = f" — capped at [cyan]{total}[/cyan]" if limit and shown > total else ""
    console.print(f"\n[bold]Found [green]{shown}[/green] books to review{cap_note}.[/bold]\n")

    locked = skipped = 0
    approve_all = False  # set to True when user chooses [A]ll remaining

    for idx, book in enumerate(books_sorted, 1):
        tags    = tags_map.get(book.id, [])
        details = details_map.get(book.id)

        description = _strip_html(details.existing_comments) if details and details.existing_comments else ""
        series      = ""
        if details and details.series:
            series = details.series
            if details.series_index is not None:
                try:
                    si = details.series_index
                    si_str = str(int(si)) if si == int(si) else str(si)
                    series = f"{details.series} #{si_str}"
                except (TypeError, ValueError):
                    pass
        year      = (details.pubdate    if details else "") or ""
        publisher = (details.publisher  if details else "") or ""
        lcc_sum   = lcc_summary_map.get(book.id, "")
        lcc_pri   = lcc_primary_map.get(book.id, "")
        lcc_sec   = lcc_secondary_map.get(book.id, "")

        console.print(_book_panel(book, tags, description, series, year, publisher, lcc_sum, f"Book {idx}/{total}"))

        # ── 3. AI assessment ──────────────────────────────────────────────────
        suggestion: TagsReviewSuggestion | None = None
        if not no_ai and ai is not None:
            with console.status("[cyan]AI assessing tags…"):
                try:
                    suggestion = ai.suggest_tags_review(
                        book=book,
                        current_tags=tags,
                        description=description,
                        series=series,
                        year=year,
                        publisher=publisher,
                        lcc_summary=lcc_sum,
                        lcc_primary=lcc_pri,
                        lcc_secondary=lcc_sec,
                    )
                except Exception as e:
                    console.print(f"[yellow]AI failed: {e}[/yellow]")

        if suggestion:
            _show_assessment(suggestion)
            # Honour approve_all: apply this book's AI suggestion silently
            if approve_all:
                final_tags = suggestion.proposed_tags
                db.apply_tags(book.id, final_tags)
                db.mark_mqg_complete([book.id], reviewed_column)
                console.print(f"[green]✓[/green] [dim]Auto-approved.[/dim]  [dim]{', '.join(final_tags)}[/dim]\n")
                locked += 1
                continue
            if (auto_approve_complete
                    and suggestion.assessment == "complete"
                    and suggestion.confidence == "high"
                    and not suggestion.added
                    and not suggestion.removed):
                console.print("[dim]  Auto-approving (complete · high confidence).[/dim]")
                db.mark_mqg_complete([book.id], reviewed_column)
                console.print(f"[green]✓[/green] Locked.\n")
                locked += 1
                continue

        # ── 4. Prompt ─────────────────────────────────────────────────────────
        choice = _prompt_action(has_ai=suggestion is not None)

        if choice == "q":
            console.print("\n[dim]Review session ended.[/dim]")
            break
        elif choice == "s":
            skipped += 1
            console.print("[dim]Skipped.[/dim]\n")
            continue
        elif choice == "A" and suggestion:
            # Approve this book and set flag for all subsequent
            approve_all = True
            final_tags = suggestion.proposed_tags
            db.apply_tags(book.id, final_tags)
            db.mark_mqg_complete([book.id], reviewed_column)
            remaining = total - idx
            console.print(
                f"[green]✓[/green] Applied AI tags + locked.  [dim]{', '.join(final_tags)}[/dim]\n"
                f"[dim]  Approve-all active — {remaining} remaining book(s) will be auto-approved.[/dim]\n"
            )
            locked += 1
        elif choice == "a" and suggestion:
            final_tags = suggestion.proposed_tags
            db.apply_tags(book.id, final_tags)
            db.mark_mqg_complete([book.id], reviewed_column)
            console.print(f"[green]✓[/green] Applied AI tags + locked.  [dim]{', '.join(final_tags)}[/dim]\n")
            locked += 1
        elif choice == "k":
            db.mark_mqg_complete([book.id], reviewed_column)
            console.print(f"[green]✓[/green] Kept current tags + locked.\n")
            locked += 1
        elif choice == "e":
            final_tags = _inline_edit(tags, suggestion.proposed_tags if suggestion else None)
            db.apply_tags(book.id, final_tags)
            db.mark_mqg_complete([book.id], reviewed_column)
            console.print(f"[green]✓[/green] Applied edited tags + locked.  [dim]{', '.join(final_tags)}[/dim]\n")
            locked += 1

    console.print(
        f"\n[bold green]Session complete.[/bold green] "
        f"[green]{locked}[/green] locked, [dim]{skipped}[/dim] skipped."
    )
