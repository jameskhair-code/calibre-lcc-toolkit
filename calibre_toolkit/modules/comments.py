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
from ..usage import format_summary
from ..db import CalibreDB
from ..logging_config import audit_log

if TYPE_CHECKING:
    from ..db import BookDetails

console = Console()

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

        table.add_row(str(i), Text(icon, style=style), score_text, book_text, preview)

    return table


def _print_full_suggestion(s: CommentsSuggestion, label: str | None = None) -> None:
    if label:
        console.print(f"\n[bold magenta]═══ {label} ═══[/bold magenta]")
    else:
        console.rule(f"[bold]{s.title}[/bold]")

    console.print(f"  [dim]{s.authors_display}[/dim]")
    icon, style = _CONF_DISPLAY.get(s.confidence, ("—", "dim"))
    type_str = f"  Type: [bold]{s.book_type or 'unknown'}[/bold]" if s.book_type else ""
    console.print(f"  Confidence: [{style}]{icon} {s.confidence}[/{style}]{type_str}")
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

    if s.must_read_score >= 0:
        score_style = _score_style(s.must_read_score)
        console.print(f"  [bold cyan]Must-Read[/bold cyan]")
        rationale = f" — {s.must_read_rationale}" if s.must_read_rationale else ""
        console.print(f"  [{score_style}]{s.must_read_score} / 10[/{score_style}]{rationale}")
        console.print()

    # HTML validation warnings (item 14). Loud red so the reviewer notices
    # before applying. Empty list = no warnings = no output.
    if s.html_warnings:
        console.print(f"  [bold red]⚠ HTML validation:[/bold red]")
        for w in s.html_warnings:
            console.print(f"    [red]- {w}[/red]")
        console.print()


def run_comments_enrichment(
    db: CalibreDB,
    ai: AIClient,
    search_query: str,
    batch_size: int = 5,
    limit: int | None = None,
    dry_run: bool = False,
    force: bool = False,
    mqg_column: str | None = None,
    mqg_manual_column: str | None = None,
    lcc_summary_column: str | None = None,
) -> None:
    """Full MQG-04 Comments enrichment flow for a Calibre search string.

    force=True bypasses the manual-skip exclusion so books previously
    flagged for manual review are still picked up.
    """

    # ── 1. Search ─────────────────────────────────────────────────────────────
    effective_query = (
        f"({search_query}) and not {mqg_manual_column}:true"
        if mqg_manual_column and not force else search_query
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
        if ai.usage.call_count > 0:
            console.print(f"[dim]{format_summary(ai.usage, step_label='comments-enrich')}[/dim]")
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

    if ai.usage.call_count > 0:
        console.print(f"[dim]{format_summary(ai.usage, step_label='comments-enrich')}[/dim]")


def _apply_batch(db: CalibreDB, suggestions: list[CommentsSuggestion]) -> list[int]:
    applied: list[int] = []
    for s in suggestions:
        with console.status(f"Writing comments for book {s.book_id}…"):
            try:
                db.apply_comments(s.book_id, s.html)
                applied.append(s.book_id)
                audit_log(
                    book_id=s.book_id,
                    field="comments",
                    new_value=s.html[:200],
                    confidence=s.confidence,
                    source="ai",
                    step="comments-enrich",
                    must_read_score=s.must_read_score,
                )
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
