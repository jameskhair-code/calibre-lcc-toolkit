"""
Author/Title cleanup module.
Orchestrates: fetch → AI suggest → display review table → confirm → apply.
"""

from __future__ import annotations
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box
from rich.prompt import Confirm, Prompt

from ..db import CalibreDB, Book
from ..ai import AIClient, CleanupSuggestion


console = Console()


def _confidence_style(confidence: str) -> tuple[str, str]:
    """Returns (emoji, Rich style) for a confidence level."""
    return {
        "high":   ("●", "green"),
        "medium": ("◑", "yellow"),
        "low":    ("○", "red"),
    }.get(confidence, ("?", "dim"))


def _diff_text(original: str, suggested: str) -> Text:
    """Show original → suggested, or just original if unchanged."""
    if original == suggested:
        return Text(original, style="dim")
    t = Text()
    t.append(original, style="red strike")
    t.append("  →  ", style="dim")
    t.append(suggested, style="green bold")
    return t


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

        table.add_row(
            str(i),
            conf_text,
            title_cell,
            author_cell,
            s.notes or "",
        )
    return table


def run_cleanup(
    db: CalibreDB,
    ai: AIClient,
    search_query: str,
    batch_size: int = 50,
    auto_apply_high: bool = False,
) -> None:
    """Full Author/Title cleanup flow for a given Calibre search string."""

    # ── 1. Fetch ──────────────────────────────────────────────────────────────
    with console.status(f"[cyan]Searching library:[/] {search_query}"):
        books = db.search(search_query)

    if not books:
        console.print("[yellow]No books matched that search. Nothing to do.[/yellow]")
        raise typer.Exit()

    console.print(f"\n[bold]Found [green]{len(books)}[/green] books.[/bold]")

    # ── 2. AI analysis ────────────────────────────────────────────────────────
    total_batches = (len(books) + batch_size - 1) // batch_size
    console.print(
        f"Sending to AI in [cyan]{total_batches}[/cyan] batch(es) "
        f"of up to [cyan]{batch_size}[/cyan] books each…\n"
    )

    all_suggestions: list[CleanupSuggestion] = []
    batches = [books[i:i + batch_size] for i in range(0, len(books), batch_size)]
    for idx, batch in enumerate(batches, 1):
        with console.status(f"[cyan]Processing batch {idx}/{total_batches}…"):
            suggestions = ai.suggest_cleanup(batch, batch_size=batch_size)
            all_suggestions.extend(suggestions)

    changes = [s for s in all_suggestions if s.any_change]
    no_changes = [s for s in all_suggestions if not s.any_change]

    console.print(
        f"[bold]Results:[/bold] "
        f"[green]{len(changes)} changes suggested[/green], "
        f"[dim]{len(no_changes)} already clean[/dim].\n"
    )

    if not changes:
        console.print("[green]Everything looks good — no changes needed![/green]")
        raise typer.Exit()

    # ── 3. Review table ───────────────────────────────────────────────────────
    table = _build_review_table(changes)
    console.print(table)

    console.print(
        "\n[dim]Legend: [green]●[/green] High confidence  "
        "[yellow]◑[/yellow] Medium  [red]○[/red] Low (review carefully)[/dim]\n"
    )

    # ── 4. Apply options ──────────────────────────────────────────────────────
    high = [s for s in changes if s.confidence == "high"]
    medium_low = [s for s in changes if s.confidence != "high"]

    if auto_apply_high and high:
        console.print(
            f"[bold]--auto-apply-high[/bold]: applying [green]{len(high)}[/green] "
            f"high-confidence changes automatically.\n"
        )
        _apply_suggestions(db, high)

        if medium_low:
            console.print(
                f"\n[yellow]{len(medium_low)}[/yellow] medium/low-confidence changes "
                "require your decision:\n"
            )
            _prompt_and_apply(db, medium_low)
    else:
        choice = Prompt.ask(
            "[bold]Apply changes?[/bold]",
            choices=["all", "high-only", "review", "skip"],
            default="review",
            show_choices=True,
        )
        if choice == "skip":
            console.print("[dim]No changes applied.[/dim]")
            raise typer.Exit()
        elif choice == "all":
            _apply_suggestions(db, changes)
        elif choice == "high-only":
            if high:
                _apply_suggestions(db, high)
                if medium_low:
                    console.print(
                        f"\n[yellow]{len(medium_low)}[/yellow] medium/low-confidence "
                        "changes were skipped. Run again to review them."
                    )
            else:
                console.print("[dim]No high-confidence changes to apply.[/dim]")
        elif choice == "review":
            _prompt_and_apply(db, changes)

    console.print("\n[bold green]Done![/bold green]")


def _apply_suggestions(db: CalibreDB, suggestions: list[CleanupSuggestion]) -> None:
    success = 0
    for s in suggestions:
        with console.status(f"Updating book {s.book_id}…"):
            try:
                db.apply_metadata(
                    book_id=s.book_id,
                    title=s.suggested_title if s.title_changed else None,
                    authors=s.suggested_authors if s.authors_changed else None,
                )
                success += 1
            except RuntimeError as e:
                console.print(f"[red]Error on book {s.book_id}: {e}[/red]")
    console.print(f"[green]Applied {success}/{len(suggestions)} changes.[/green]")


def _prompt_and_apply(db: CalibreDB, suggestions: list[CleanupSuggestion]) -> None:
    """Walk through each suggestion and let the user accept, skip, or edit."""
    to_apply: list[CleanupSuggestion] = []

    for s in suggestions:
        console.rule(f"[bold]Book {s.book_id}[/bold]")
        icon, style = _confidence_style(s.confidence)
        console.print(f"Confidence: [{style}]{icon} {s.confidence}[/{style}]")
        if s.title_changed:
            console.print(f"  Title:   {_diff_text(s.original_title, s.suggested_title)}")
        if s.authors_changed:
            console.print(
                f"  Authors: {_diff_text(' & '.join(s.original_authors), ' & '.join(s.suggested_authors))}"
            )
        if s.notes:
            console.print(f"  Notes:   [dim]{s.notes}[/dim]")

        choice = Prompt.ask("  Action", choices=["y", "n", "e"], default="y",
                            show_choices=True,
                            show_default=True)
        # y=accept, n=skip, e=edit manually
        if choice == "y":
            to_apply.append(s)
        elif choice == "e":
            new_title = Prompt.ask("  New title", default=s.suggested_title)
            new_authors_raw = Prompt.ask(
                "  New authors (separate with &)", default=" & ".join(s.suggested_authors)
            )
            s.suggested_title = new_title.strip()
            s.suggested_authors = [a.strip() for a in new_authors_raw.split("&")]
            s.title_changed = s.suggested_title != s.original_title
            s.authors_changed = s.suggested_authors != s.original_authors
            to_apply.append(s)

    if to_apply:
        _apply_suggestions(db, to_apply)
    else:
        console.print("[dim]No changes applied.[/dim]")
