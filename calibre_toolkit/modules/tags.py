"""
MQG-05 Tags Enrichment module.
Orchestrates: read current tags + LCC context → AI propose → display → confirm → write.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.prompt import Prompt

from ..ai import AIClient, TagsSuggestion
from ..db import CalibreDB

console = Console()

_CONF_DISPLAY = {
    "high":   ("●", "green"),
    "medium": ("◐", "yellow"),
    "low":    ("○", "red"),
}


def _build_review_table(suggestions: list[TagsSuggestion]) -> Table:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
                  expand=True, show_lines=True)
    table.add_column("#",        style="dim", width=4, no_wrap=True)
    table.add_column("Conf",     width=5, no_wrap=True)
    table.add_column("Book",     ratio=2)
    table.add_column("Current",  ratio=3)
    table.add_column("Proposed", ratio=3)

    for i, s in enumerate(suggestions, 1):
        icon, style = _CONF_DISPLAY.get(s.confidence, ("—", "dim"))

        book_text = Text()
        book_text.append(s.title)
        book_text.append(f"\n{s.authors_display}", style="dim")

        current_text = Text(
            ", ".join(s.current_tags) if s.current_tags else "(none)",
            style="dim"
        )

        proposed_text = Text()
        proposed_text.append(", ".join(s.proposed_tags) or "(none)")
        if s.notes:
            proposed_text.append(f"\n↳ {s.notes}", style="dim italic")

        table.add_row(str(i), Text(icon, style=style), book_text, current_text, proposed_text)

    return table


def run_tags_enrichment(
    db: CalibreDB,
    ai: AIClient,
    search_query: str,
    batch_size: int = 20,
    limit: int | None = None,
    dry_run: bool = False,
    mqg_column: str | None = None,
    mqg_manual_column: str | None = None,
    lcc_summary_column: str | None = None,
    lcc_secondary_column: str | None = None,
    lcc_primary_column: str | None = None,
) -> None:
    """Full MQG-05 Tags enrichment flow for a Calibre search string."""

    # ── 1. Search ─────────────────────────────────────────────────────────────
    effective_query = (
        f"({search_query}) and not {mqg_manual_column}:true"
        if mqg_manual_column else search_query
    )
    try:
        with console.status(f"[cyan]Searching library:[/] {search_query}"):
            books = db.search(effective_query)
    except RuntimeError as e:
        console.print(Panel(str(e), title="[red]Cannot access library[/red]", border_style="red"))
        raise typer.Exit(1)

    if not books:
        console.print("[yellow]No books matched that search. Nothing to do.[/yellow]")
        raise typer.Exit()

    total_matched = len(books)
    if limit and len(books) > limit:
        books = books[:limit]
        console.print(
            f"\n[bold]Found [green]{total_matched}[/green] books "
            f"— processing first [cyan]{limit}[/cyan] (--limit).[/bold]"
        )
    else:
        console.print(f"\n[bold]Found [green]{len(books)}[/green] books.[/bold]")

    # ── 2. Read current tags and LCC context ──────────────────────────────────
    book_ids = [b.id for b in books]
    with console.status("[cyan]Reading current tags and LCC context…"):
        tags_map = db.get_tags_batch(book_ids)
        context_map: dict[int, dict[str, str]] = {bid: {} for bid in book_ids}
        for col_key, col_label in [
            ("lcc_summary",        lcc_summary_column),
            ("lcc_secondary_class", lcc_secondary_column),
            ("lcc_primary_class",   lcc_primary_column),
        ]:
            if col_label:
                batch = db.get_custom_column_batch(book_ids, col_label)
                for bid, val in batch.items():
                    context_map[bid][col_key] = val

    # ── 3. AI generation ───────────────────────────────────────────────────────
    with console.status(
        f"[cyan]Generating tags for {len(books)} book(s) "
        f"in batches of {batch_size}…[/cyan]"
    ):
        try:
            suggestions = ai.suggest_tags(books, tags_map, context_map, batch_size=batch_size)
        except RuntimeError as e:
            console.print(Panel(str(e), title="[red]AI generation failed[/red]", border_style="red"))
            raise typer.Exit(1)

    if not suggestions:
        console.print("[yellow]AI returned no suggestions.[/yellow]")
        raise typer.Exit(1)

    high   = [s for s in suggestions if s.confidence == "high"]
    medium = [s for s in suggestions if s.confidence == "medium"]
    low    = [s for s in suggestions if s.confidence == "low"]

    console.print(
        f"\n[bold]Results:[/bold] "
        f"[green]{len(high)} high[/green], "
        f"[yellow]{len(medium)} medium[/yellow], "
        f"[red]{len(low)} low[/red]\n"
    )

    # ── 4. Dry-run or display review table ────────────────────────────────────
    if dry_run:
        console.print("[bold cyan]── Dry-run: proposed tags (no writes) ──[/bold cyan]\n")
        console.print(_build_review_table(suggestions))
        changed = sum(1 for s in suggestions if s.tags_changed)
        console.print(
            f"\n[dim]Dry-run complete — {len(suggestions)} book(s) shown, "
            f"{changed} would change. No writes.[/dim]"
        )
        return

    console.print(_build_review_table(suggestions))
    console.print(
        "\n[dim]Legend: [green]●[/green] high  "
        "[yellow]◐[/yellow] medium  [red]○[/red] low\n"
        "Current tags shown for reference — proposed tags replace them.[/dim]\n"
    )

    # ── 5. Apply ───────────────────────────────────────────────────────────────
    applied_ids: list[int] = []
    declined: list[TagsSuggestion] = []

    if high:
        choice = Prompt.ask(
            f"\n[bold]Tier 1:[/bold] Apply {len(high)} high-confidence "
            f"tag set{'s' if len(high) != 1 else ''}?",
            choices=["all", "review", "skip"], default="all", show_choices=True,
        )
        if choice == "all":
            applied_ids += _apply_batch(db, high)
        elif choice == "review":
            a, d = _prompt_and_apply(db, high)
            applied_ids += a
            declined += d

    if medium:
        choice = Prompt.ask(
            f"\n[bold yellow]Tier 2:[/bold yellow] Apply {len(medium)} medium-confidence "
            f"tag set{'s' if len(medium) != 1 else ''}?",
            choices=["all", "review", "skip"], default="review", show_choices=True,
        )
        if choice == "all":
            applied_ids += _apply_batch(db, medium)
        elif choice == "review":
            a, d = _prompt_and_apply(db, medium)
            applied_ids += a
            declined += d

    if low:
        choice = Prompt.ask(
            f"\n[bold red]Tier 3:[/bold red] Apply {len(low)} low-confidence "
            f"tag set{'s' if len(low) != 1 else ''}?",
            choices=["all", "review", "skip"], default="skip", show_choices=True,
        )
        if choice == "all":
            applied_ids += _apply_batch(db, low)
        elif choice == "review":
            a, d = _prompt_and_apply(db, low)
            applied_ids += a
            declined += d
        else:
            declined += low

    # ── 6. Mark MQG ───────────────────────────────────────────────────────────
    high_applied = [s.book_id for s in high if s.book_id in applied_ids]
    if mqg_column and high_applied:
        _mark_complete(db, mqg_column, high_applied, label="MQG-05")

    manual_ids = [s.book_id for s in declined]
    if mqg_manual_column and manual_ids:
        console.print(
            f"\n[yellow]Flagging {len(manual_ids)} book(s)[/yellow] in "
            f"[bold]{mqg_manual_column}[/bold] for manual review."
        )
        with console.status("Flagging…"):
            db.mark_mqg_complete(manual_ids, mqg_manual_column)

    console.print(
        f"\n[bold green]Done![/bold green] "
        f"[green]{len(applied_ids)}[/green] applied, "
        f"[green]{len(high_applied)}[/green] marked MQG-05 complete"
        + (f", [yellow]{len(manual_ids)}[/yellow] flagged for manual" if manual_ids else "")
        + "."
    )


def _apply_batch(db: CalibreDB, suggestions: list[TagsSuggestion]) -> list[int]:
    applied: list[int] = []
    for s in suggestions:
        with console.status(f"Writing tags for book {s.book_id}…"):
            try:
                db.apply_tags(s.book_id, s.proposed_tags)
                applied.append(s.book_id)
            except RuntimeError as e:
                console.print(f"[red]Error on book {s.book_id}: {e}[/red]")
    console.print(f"[green]Applied {len(applied)}/{len(suggestions)} tag sets.[/green]")
    return applied


def _prompt_and_apply(
    db: CalibreDB,
    suggestions: list[TagsSuggestion],
) -> tuple[list[int], list[TagsSuggestion]]:
    to_apply: list[TagsSuggestion] = []
    declined: list[TagsSuggestion] = []

    for s in suggestions:
        console.rule(f"[bold]Book {s.book_id}[/bold]")
        console.print(f"  [bold]{s.title}[/bold]  [dim]{s.authors_display}[/dim]")
        icon, style = _CONF_DISPLAY.get(s.confidence, ("—", "dim"))
        console.print(f"  Confidence: [{style}]{icon} {s.confidence}[/{style}]")
        if s.current_tags:
            console.print(f"  Current:  [dim]{', '.join(s.current_tags)}[/dim]")
        console.print(f"  Proposed: [bold]{', '.join(s.proposed_tags)}[/bold]")
        if s.notes:
            console.print(f"  [dim]{s.notes}[/dim]")

        default = "n" if s.confidence == "low" else "y"
        choice = Prompt.ask(
            "  Apply?", choices=["y", "n"], default=default,
            show_choices=True, show_default=True,
        )
        if choice == "y":
            to_apply.append(s)
        else:
            declined.append(s)
            console.print("  [dim]Declined — will be flagged for manual review.[/dim]")

    applied = _apply_batch(db, to_apply) if to_apply else []
    return applied, declined


def _mark_complete(
    db: CalibreDB, mqg_column: str, book_ids: list[int], label: str
) -> None:
    if not mqg_column or not book_ids:
        return
    with console.status(f"[cyan]Marking {len(book_ids)} books as {label} complete…"):
        db.mark_mqg_complete(book_ids, mqg_column)
    console.print(
        f"[dim]Marked {len(book_ids)} books complete in [bold]{mqg_column}[/bold].[/dim]"
    )
