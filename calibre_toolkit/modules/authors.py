"""
Author/Title cleanup module.
Orchestrates: fetch → AI suggest → display review table → confirm → apply.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.prompt import Prompt

from datetime import datetime
from time import monotonic

from ..db import CalibreDB, Book
from ..ai import AIClient, CleanupSuggestion
from ..review_prompts import confirm_bulk_apply
from ..summary import StepSummary, render_summary_panel


console = Console()


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


def run_cleanup(
    db: CalibreDB,
    ai: AIClient,
    search_query: str,
    batch_size: int = 50,
    auto_apply_high: bool = False,
    mqg_column: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    apply_confirm_threshold: int = 20,
) -> None:
    """Full Author/Title cleanup flow for a given Calibre search string."""
    _started_at = datetime.now()
    _t0 = monotonic()

    # ── 1. Fetch ──────────────────────────────────────────────────────────────
    try:
        with console.status(f"[cyan]Searching library:[/] {search_query}"):
            books = db.search(search_query)
    except RuntimeError as e:
        console.print(Panel(str(e), title="[red]Cannot access library[/red]", border_style="red"))
        raise typer.Exit(1)

    if not books:
        console.print("[yellow]No books matched that search. Nothing to do.[/yellow]")
        raise typer.Exit()

    if limit is not None:
        books = books[:limit]

    console.print(f"\n[bold]Found [green]{len(books)}[/green] books.[/bold]")

    # ── 2. AI analysis (concurrent batches, partial-failure tolerant) ────────
    total_batches = (len(books) + batch_size - 1) // batch_size
    console.print(
        f"Sending to AI in [cyan]{total_batches}[/cyan] batch(es) "
        f"of [cyan]{batch_size}[/cyan] books "
        f"([cyan]{ai.max_concurrency}[/cyan] in flight)…\n"
    )

    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn, TimeElapsedColumn
    all_suggestions: list[CleanupSuggestion] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]Books processed"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TextColumn("[red]{task.fields[failed]} failed"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("ai", total=len(books), failed=0)

        def _on_progress(done_batches, total_batches, failed):
            progress.update(task, completed=min(done_batches * batch_size, len(books)), failed=failed)

        all_suggestions = ai.suggest_cleanup(books, batch_size=batch_size, progress_callback=_on_progress)

    if ai.last_failures:
        console.print(
            f"[red]Warning: {len(ai.last_failures)} of {total_batches} batches failed.[/red]"
        )
        for f in ai.last_failures:
            console.print(
                f"  [dim]Batch {f.batch_index+1} ({len(f.book_ids)} books): {f.error[:200]}[/dim]"
            )
        console.print(
            "  [dim]Books in failed batches will not be marked complete — re-run to retry them.[/dim]\n"
        )

    gated_count = _gate_author_removals(all_suggestions)

    changes = [s for s in all_suggestions if s.any_change]
    no_changes = [s for s in all_suggestions if not s.any_change]

    console.print(
        f"[bold]Results:[/bold] "
        f"[green]{len(changes)} changes suggested[/green], "
        f"[dim]{len(no_changes)} already clean[/dim].\n"
    )

    if gated_count:
        console.print(
            f"[yellow]⚠ {gated_count} suggestion(s) remove an author — capped to "
            "low confidence and review-only; they will not auto-apply.[/yellow]\n"
        )

    # Books already clean → mark MQG complete immediately
    clean_ids = [s.book_id for s in no_changes]

    if not changes:
        console.print("[green]Everything looks good — no changes needed![/green]")
        if not dry_run:
            _mark_complete(db, mqg_column, clean_ids, label="already-clean")
        raise typer.Exit()

    # ── 3. Review table ───────────────────────────────────────────────────────
    table = _build_review_table(changes)
    console.print(table)
    console.print(
        "\n[dim]Legend: [green]●[/green] High confidence  "
        "[yellow]◑[/yellow] Medium  [red]○[/red] Low (review carefully)[/dim]\n"
    )

    if dry_run:
        console.print(
            "[bold cyan]── Dry-run: proposed changes shown above (no writes) ──[/bold cyan]"
        )
        console.print(render_summary_panel(
            StepSummary(
                step_label="clean-titles",
                started_at=_started_at,
                elapsed_seconds=monotonic() - _t0,
                applied_high=sum(1 for s in changes if s.confidence == "high"),
                applied_medium=sum(1 for s in changes if s.confidence == "medium"),
                applied_low=sum(1 for s in changes if s.confidence == "low"),
                skipped_already_done=len(no_changes),
                usage=ai.usage,
            ),
            dry_run=True,
        ))
        return

    # ── 4. Apply options ──────────────────────────────────────────────────────
    high = [s for s in changes if s.confidence == "high"]
    medium_low = [s for s in changes if s.confidence != "high"]
    applied_ids: list[int] = []

    if auto_apply_high and high:
        console.print(
            f"[bold]--auto-apply-high[/bold]: applying [green]{len(high)}[/green] "
            f"high-confidence changes automatically.\n"
        )
        applied_ids += _apply_suggestions(db, high)
        if medium_low:
            console.print(
                f"\n[yellow]{len(medium_low)}[/yellow] medium/low-confidence changes "
                "require your decision:\n"
            )
            applied_ids += _prompt_and_apply(db, medium_low)
    else:
        console.print("[dim]Waiting for input…[/dim]")
        choice = Prompt.ask(
            "[bold]Apply changes?[/bold]  \\[a]ll / \\[h]igh-only / \\[r]eview / \\[s]kip",
            choices=["all", "high-only", "review", "skip", "a", "h", "r", "s"],
            default="review",
            show_choices=False,
        )
        choice = {"a": "all", "h": "high-only", "r": "review", "s": "skip"}.get(choice, choice)
        if choice == "skip":
            console.print("[dim]No changes applied.[/dim]")
            raise typer.Exit()
        elif choice == "all":
            gated = [s for s in changes if s.removes_author]
            bulk = [s for s in changes if not s.removes_author]
            proceed = True
            if bulk:
                if confirm_bulk_apply(len(bulk), apply_confirm_threshold, console):
                    applied_ids += _apply_suggestions(db, bulk)
                else:
                    console.print("[dim]Bulk apply cancelled. No changes applied.[/dim]")
                    proceed = False
            if proceed and gated:
                console.print(
                    f"\n[yellow]{len(gated)} author-removal change(s) are never "
                    "bulk-applied — review each:[/yellow]\n"
                )
                applied_ids += _prompt_and_apply(db, gated)
        elif choice == "high-only":
            if high:
                applied_ids += _apply_suggestions(db, high)
                if medium_low:
                    console.print(
                        f"\n[yellow]{len(medium_low)}[/yellow] medium/low-confidence "
                        "changes were skipped. Run again to review them."
                    )
            else:
                console.print("[dim]No high-confidence changes to apply.[/dim]")
        elif choice == "review":
            applied_ids += _prompt_and_apply(db, changes)

    # ── 5. Mark MQG complete ──────────────────────────────────────────────────
    _mark_complete(db, mqg_column, clean_ids + applied_ids, label="processed")

    applied_ids_set = set(applied_ids)
    declined_count = sum(1 for s in changes if s.book_id not in applied_ids_set)
    console.print(render_summary_panel(
        StepSummary(
            step_label="clean-titles",
            started_at=_started_at,
            elapsed_seconds=monotonic() - _t0,
            applied_high=sum(1 for s in changes if s.confidence == "high" and s.book_id in applied_ids_set),
            applied_medium=sum(1 for s in changes if s.confidence == "medium" and s.book_id in applied_ids_set),
            applied_low=sum(1 for s in changes if s.confidence == "low" and s.book_id in applied_ids_set),
            skipped_already_done=len(no_changes),
            skipped_declined=declined_count,
            usage=ai.usage,
        ),
    ))


def _apply_suggestions(db: CalibreDB, suggestions: list[CleanupSuggestion]) -> list[int]:
    """Apply a list of suggestions in parallel. Returns IDs of successfully updated books."""
    if not suggestions:
        return []

    updates = [
        (
            s.book_id,
            s.suggested_title if s.title_changed else None,
            s.suggested_authors if s.authors_changed else None,
        )
        for s in suggestions
    ]

    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn, TimeElapsedColumn

    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]Applying"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TextColumn("[red]{task.fields[failed]} failed"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("apply", total=len(updates), failed=0)

        def _on_progress(done, total, failed):
            progress.update(task, completed=done, failed=failed)

        applied, failures = db.apply_metadata_batch(updates, progress_callback=_on_progress)

    for book_id, err in failures:
        console.print(f"[red]Error on book {book_id}: {err}[/red]")
    console.print(f"[green]Applied {len(applied)}/{len(suggestions)} changes.[/green]")
    return applied


def _prompt_and_apply(db: CalibreDB, suggestions: list[CleanupSuggestion]) -> list[int]:
    """Walk through each suggestion one by one. Returns IDs of accepted books."""
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
        if s.removes_author:
            console.print(
                "  [bold red]⚠ This removes an author — verify against a trusted "
                "source before applying.[/bold red]"
            )
        if s.notes:
            console.print(f"  Notes:   [dim]{s.notes}[/dim]")

        choice = Prompt.ask("  Action", choices=["y", "n", "e"], default="y",
                            show_choices=True, show_default=True)
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
        return _apply_suggestions(db, to_apply)
    else:
        console.print("[dim]No changes applied.[/dim]")
        return []


def _mark_complete(
    db: CalibreDB,
    mqg_column: str | None,
    book_ids: list[int],
    label: str = "processed",
) -> None:
    if not mqg_column or not book_ids:
        return
    with console.status(f"[cyan]Marking {len(book_ids)} {label} books as MQG-01 complete…"):
        db.mark_mqg_complete(book_ids, mqg_column)
    console.print(
        f"[dim]Marked {len(book_ids)} books as complete in [bold]{mqg_column}[/bold].[/dim]"
    )
