"""tags-review — MQG-05 interactive per-book tag review with locking.

Handler + orchestration (search → per-book panel → AI assessment → prompt →
write + lock). Pure domain helpers (HTML stripping, the book panel builder)
live in `modules/tags_review.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Annotated, TYPE_CHECKING

import typer
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt

from ._common import (
    app, console, DEFAULT_CONFIG_PATH,
    _load_config, _make_db, _make_ai,
)
from ..modules.tags_review import _book_panel, _strip_html
from ..usage import format_summary

if TYPE_CHECKING:
    from ..ai import AIClient, TagsReviewSuggestion
    from ..db import CalibreDB


@app.command(
    epilog=(
        "Examples:\n\n"
        "  calibre-toolkit tags-review\n\n"
        '  calibre-toolkit tags-review "tag:Booker" --limit 20\n\n'
        "  calibre-toolkit tags-review --no-ai --limit 50\n\n"
        "  calibre-toolkit tags-review --auto-apply-high --limit 100\n"
    ),
)
def tags_review(
    search: Annotated[
        Optional[str],
        typer.Argument(
            help="Calibre search string (default: books where #tags_reviewed is not set)"
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-n", help="Max books per session"),
    ] = None,
    no_ai: Annotated[
        bool,
        typer.Option("--no-ai", help="Skip AI assessment; manual review only"),
    ] = False,
    auto_approve: Annotated[
        bool,
        typer.Option(
            "--auto-apply-high", "--auto-approve",
            help="Auto-lock books where AI says complete + high confidence "
                 "(--auto-approve is a deprecated alias)",
        ),
    ] = False,
    ai_provider: Annotated[
        Optional[str],
        typer.Option("--ai-provider", help="Override AI provider for this run"),
    ] = None,
    ai_model: Annotated[
        Optional[str],
        typer.Option("--ai-model", help="Override AI model. Accepts an alias (fast / latest / legacy) or a literal model ID."),
    ] = None,
):
    """
    MQG-05: Interactive per-book tag review with AI assessment and locking.

    For each unreviewed book, shows the full metadata context (title, authors,
    description, current tags, LCC classification) and runs an AI assessment
    of tag completeness. You choose to:

      [a] approve AI suggestions (apply proposed tags + lock)
      [k] keep current tags as-is (lock without changes)
      [e] edit tags inline (pre-filled from AI suggestion, then lock)
      [s] skip this book (leave unreviewed)
      [q] quit the session

    Books are ordered by tag count ascending (fewest tags first).
    The #tags_reviewed column is set to Yes for every locked book.
    """
    cfg = _load_config(config)
    db  = _make_db(cfg)
    ai  = (
        _make_ai(cfg, command_key="tags", provider_override=ai_provider, model_override=ai_model)
        if not no_ai else None
    )

    tags_cfg = cfg.get("tags", {})
    lcc_cfg  = cfg.get("lcc",  {})
    reviewed_column = tags_cfg.get("reviewed_column", "#tags_reviewed")

    effective_search = search or f"not {reviewed_column}:true"

    _base = cfg.get("ai", {})
    _effective_model = ai_model or {**_base, **_base.get("tags", {})}.get("model", "(default)")

    mode_label = "Manual only" if no_ai else _effective_model
    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — MQG-05 Tags Review\n\n",
                ("Search:   ", "dim"),
                (effective_search, "bold"),
                ("\nProvider: ", "dim"),
                (mode_label, "bold"),
                ("\nColumn:   ", "dim"),
                (reviewed_column, "bold"),
            ),
            border_style="cyan",
        )
    )

    run_tags_review(
        db=db,
        ai=ai,
        search_query=effective_search,
        reviewed_column=reviewed_column,
        mqg_column=tags_cfg.get("mqg_column"),
        lcc_summary_column=lcc_cfg.get("lcc_summary_column", "#lcc_summary"),
        lcc_primary_column=lcc_cfg.get("primary_class_column", "#lcc_primary_class"),
        lcc_secondary_column=lcc_cfg.get("secondary_class_column", "#lcc_secondary_class"),
        limit=limit,
        no_ai=no_ai,
        auto_approve_complete=auto_approve,
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


def _lock(db: CalibreDB, book_id: int, reviewed_column: str, mqg_column: str | None) -> None:
    """Mark a book as reviewed and (if configured) as MQG-05 complete."""
    db.mark_mqg_complete([book_id], reviewed_column)
    if mqg_column:
        db.mark_mqg_complete([book_id], mqg_column)


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
    mqg_column: str | None = None,
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
                _lock(db, book.id, reviewed_column, mqg_column)
                console.print(f"[green]✓[/green] [dim]Auto-approved.[/dim]  [dim]{', '.join(final_tags)}[/dim]\n")
                locked += 1
                continue
            if (auto_approve_complete
                    and suggestion.assessment == "complete"
                    and suggestion.confidence == "high"
                    and not suggestion.added
                    and not suggestion.removed):
                console.print("[dim]  Auto-approving (complete · high confidence).[/dim]")
                _lock(db, book.id, reviewed_column, mqg_column)
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
            _lock(db, book.id, reviewed_column, mqg_column)
            remaining = total - idx
            console.print(
                f"[green]✓[/green] Applied AI tags + locked.  [dim]{', '.join(final_tags)}[/dim]\n"
                f"[dim]  Approve-all active — {remaining} remaining book(s) will be auto-approved.[/dim]\n"
            )
            locked += 1
        elif choice == "a" and suggestion:
            final_tags = suggestion.proposed_tags
            db.apply_tags(book.id, final_tags)
            _lock(db, book.id, reviewed_column, mqg_column)
            console.print(f"[green]✓[/green] Applied AI tags + locked.  [dim]{', '.join(final_tags)}[/dim]\n")
            locked += 1
        elif choice == "k":
            _lock(db, book.id, reviewed_column, mqg_column)
            console.print(f"[green]✓[/green] Kept current tags + locked.\n")
            locked += 1
        elif choice == "e":
            final_tags = _inline_edit(tags, suggestion.proposed_tags if suggestion else None)
            db.apply_tags(book.id, final_tags)
            _lock(db, book.id, reviewed_column, mqg_column)
            console.print(f"[green]✓[/green] Applied edited tags + locked.  [dim]{', '.join(final_tags)}[/dim]\n")
            locked += 1

    console.print(
        f"\n[bold green]Session complete.[/bold green] "
        f"[green]{locked}[/green] locked, [dim]{skipped}[/dim] skipped."
    )

    if ai is not None and ai.usage.call_count > 0:
        console.print(f"[dim]{format_summary(ai.usage, step_label='tags-review')}[/dim]")
