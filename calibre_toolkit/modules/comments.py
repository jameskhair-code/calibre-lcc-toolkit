"""
MQG-04 Comments Enrichment module.
Orchestrates: read book details → AI generate → display review → confirm → write.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.prompt import Prompt

from ..ai import AIClient, CommentsSuggestion
from ..db import CalibreDB

if TYPE_CHECKING:
    from ..db import BookDetails

console = Console()

_CONF_DISPLAY = {
    "high":   ("●", "green"),
    "medium": ("◐", "yellow"),
    "low":    ("○", "red"),
}

_SECTION_LABELS = [
    ("the_book",                     "The Book"),
    ("something_you_might_not_know", "Something You Might Not Know"),
    ("why_read_it",                  "Why Read It"),
]

# Three tone variants for --tone-test
_TONE_VARIANTS = [
    (
        "witty-opinionated",
        "Voice: Christopher Hitchens / P.J. O'Rourke. Opinionated, direct, specific. "
        "Do not hedge. Name the argument. Push back on fashionable framings where the "
        "book allows. 'Why Read It' should sound like a recommendation from a well-read "
        "friend who has strong opinions and isn't afraid to use them.",
    ),
    (
        "neutral-professional",
        "Voice: Standard library catalog style. Factual, objective, no personality. "
        "Avoid evaluative language. Describe the book's subject and argument without "
        "endorsing or critiquing it. The reader should not be able to tell whether the "
        "author is worth reading.",
    ),
    (
        "warm-accessible",
        "Voice: Warm and conversational, written for a curious reader who reads broadly "
        "but is not a specialist. Approachable, enthusiastic without being breathless. "
        "'Why Read It' should feel like a genuine, friendly recommendation.",
    ),
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _truncate(text: str, max_chars: int = 130) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def _build_review_table(suggestions: list[CommentsSuggestion]) -> Table:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
                  expand=True, show_lines=True)
    table.add_column("#",      style="dim", width=4, no_wrap=True)
    table.add_column("Conf",   width=5, no_wrap=True)
    table.add_column("Book",   ratio=2)
    table.add_column("Preview", ratio=6)

    for i, s in enumerate(suggestions, 1):
        icon, style = _CONF_DISPLAY.get(s.confidence, ("—", "dim"))

        book_text = Text()
        book_text.append(s.title)
        book_text.append(f"\n{s.authors_display}", style="dim")

        preview = Text()
        for key, label in [
            ("the_book",    "Book"),
            ("why_read_it", "Sell"),
        ]:
            val = _truncate(s.sections.get(key, "") or "", 120)
            preview.append(f"{label}: ", style="dim")
            preview.append(val or "(empty)")
            preview.append("\n")
        if s.notes:
            preview.append(f"↳ {s.notes}", style="dim italic")

        table.add_row(str(i), Text(icon, style=style), book_text, preview)

    return table


def _print_full_suggestion(s: CommentsSuggestion, label: str | None = None) -> None:
    if label:
        console.print(f"\n[bold magenta]═══ {label} ═══[/bold magenta]")
    else:
        console.rule(f"[bold]{s.title}[/bold]")

    console.print(f"  [dim]{s.authors_display}[/dim]")
    icon, style = _CONF_DISPLAY.get(s.confidence, ("—", "dim"))
    console.print(f"  Confidence: [{style}]{icon} {s.confidence}[/{style}]")
    if s.notes:
        console.print(f"  [dim]{s.notes}[/dim]")
    console.print()

    for key, section_label in _SECTION_LABELS:
        text = (s.sections.get(key) or "").strip()
        if not text:
            continue
        console.print(f"  [bold cyan]{section_label}[/bold cyan]")
        console.print(f"  {text}")
        console.print()


def run_comments_enrichment(
    db: CalibreDB,
    ai: AIClient,
    search_query: str,
    batch_size: int = 5,
    limit: int | None = None,
    force: bool = False,
    dry_run: bool = False,
    tone_test: bool = False,
    mqg_column: str | None = None,
    mqg_manual_column: str | None = None,
    lcc_summary_column: str | None = None,
) -> None:
    """Full MQG-04 Comments enrichment flow for a Calibre search string."""

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

    # ── 2. Read book details ──────────────────────────────────────────────────
    book_ids = [b.id for b in books]
    with console.status("[cyan]Reading book details and existing comments…"):
        details_map = db.get_book_details_batch(book_ids)

    # Tone test: generate 3 voice variants for the first book, then exit
    if tone_test:
        _run_tone_test(db, ai, books[:1], details_map, lcc_summary_column)
        return

    # Skip books that already have comments unless --force
    if not force:
        before = len(books)
        books = [b for b in books if not details_map[b.id].existing_comments.strip()]
        skipped = before - len(books)
        if skipped:
            console.print(
                f"[dim]Skipping {skipped} book(s) — already have comments. "
                "Use --force to re-process.[/dim]"
            )
    if not books:
        console.print("[green]Nothing to do — every matched book already has comments.[/green]")
        raise typer.Exit()

    # ── 3. Read LCC summaries as optional context ─────────────────────────────
    lcc_summary_map: dict[int, str] = {}
    if lcc_summary_column:
        with console.status("[cyan]Reading LCC summaries for context…"):
            lcc_summary_map = db.get_custom_column_batch([b.id for b in books], lcc_summary_column)

    # ── 4. AI generation ───────────────────────────────────────────────────────
    with console.status(
        f"[cyan]Generating comments for {len(books)} book(s) "
        f"in batches of {batch_size}…[/cyan]"
    ):
        try:
            suggestions = ai.suggest_comments(
                books, details_map, lcc_summary_map, batch_size=batch_size
            )
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

    # ── 5. Dry-run or display review table ────────────────────────────────────
    if dry_run:
        console.print("[bold cyan]── Dry-run: proposed comments (no writes) ──[/bold cyan]\n")
        for s in suggestions:
            _print_full_suggestion(s)
        console.print(
            f"\n[dim]Dry-run complete — {len(suggestions)} book(s) shown. "
            "No changes written.[/dim]"
        )
        return

    console.print(_build_review_table(suggestions))
    console.print(
        "\n[dim]Legend: [green]●[/green] high  "
        "[yellow]◐[/yellow] medium  [red]○[/red] low"
        "  — use 'review' to read full text before deciding.[/dim]\n"
    )

    # ── 6. Apply ───────────────────────────────────────────────────────────────
    applied_ids: list[int] = []
    declined: list[CommentsSuggestion] = []

    if high:
        choice = Prompt.ask(
            f"\n[bold]Tier 1:[/bold] Apply {len(high)} high-confidence "
            f"comment{'s' if len(high) != 1 else ''}?",
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
            f"comment{'s' if len(medium) != 1 else ''}?",
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
            f"comment{'s' if len(low) != 1 else ''}?",
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

    # ── 7. Mark MQG / flag manual ─────────────────────────────────────────────
    high_applied = [s.book_id for s in high if s.book_id in applied_ids]
    if mqg_column and high_applied:
        _mark_complete(db, mqg_column, high_applied, label="MQG-04")

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
        f"[green]{len(high_applied)}[/green] marked MQG-04 complete"
        + (f", [yellow]{len(manual_ids)}[/yellow] flagged for manual" if manual_ids else "")
        + "."
    )


def _run_tone_test(
    db: CalibreDB,
    ai: AIClient,
    books: list,
    details_map: dict,
    lcc_summary_column: str | None,
) -> None:
    """Generate 3 tone variants for one book and display them for comparison."""
    book_ids = [b.id for b in books]

    lcc_summary_map: dict[int, str] = {}
    if lcc_summary_column:
        lcc_summary_map = db.get_custom_column_batch(book_ids, lcc_summary_column)

    b = books[0]
    console.print(
        f"\n[bold cyan]── Tone Test: [white]{b.title}[/white] ──[/bold cyan]\n"
        f"[dim]Generating 3 voice variants for comparison. No writes.[/dim]"
    )

    for tone_key, tone_instruction in _TONE_VARIANTS:
        console.print(f"\n[bold magenta]═══ Tone variant: {tone_key} ═══[/bold magenta]")
        with console.status(f"[cyan]Generating '{tone_key}' variant…"):
            try:
                suggestions = ai.suggest_comments(
                    books, details_map, lcc_summary_map,
                    batch_size=1, tone_override=tone_instruction
                )
            except RuntimeError as e:
                console.print(f"[red]Failed: {e}[/red]")
                continue
        if suggestions:
            _print_full_suggestion(suggestions[0])
        else:
            console.print("[red]No suggestion returned.[/red]")

    console.print(
        "\n[dim]Tone test complete — 3 variants shown. "
        "No changes written. Edit rules/reader_profile.md to lock in your preference, "
        "then run without --tone-test.[/dim]"
    )


def _apply_batch(db: CalibreDB, suggestions: list[CommentsSuggestion]) -> list[int]:
    applied: list[int] = []
    for s in suggestions:
        with console.status(f"Writing comments for book {s.book_id}…"):
            try:
                db.apply_comments(s.book_id, s.html)
                applied.append(s.book_id)
            except RuntimeError as e:
                console.print(f"[red]Error on book {s.book_id}: {e}[/red]")
    console.print(f"[green]Applied {len(applied)}/{len(suggestions)} comments.[/green]")
    return applied


def _prompt_and_apply(
    db: CalibreDB,
    suggestions: list[CommentsSuggestion],
) -> tuple[list[int], list[CommentsSuggestion]]:
    to_apply: list[CommentsSuggestion] = []
    declined: list[CommentsSuggestion] = []

    for s in suggestions:
        _print_full_suggestion(s)
        default = "n" if s.confidence == "low" else "y"
        choice = Prompt.ask(
            "  Action",
            choices=["y", "n"],
            default=default,
            show_choices=True,
            show_default=True,
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
