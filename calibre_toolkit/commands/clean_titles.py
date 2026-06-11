"""clean-titles — AI-assisted author and title cleanup.

Handler + orchestration (fetch → AI suggest → review → confirm → apply).
Pure domain helpers (diff rendering, the author-removal gate, the review
table builder) live in `modules/authors.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Annotated, TYPE_CHECKING

import typer
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt

from datetime import datetime
from time import monotonic

from ._common import (
    app, console, DEFAULT_CONFIG_PATH,
    _load_config, _make_db, _make_ai, _apply_confirm_threshold,
    _confirm_above_usd, budget_guardrail,
)
from ..modules.authors import (
    _build_review_table,
    _confidence_style,
    _diff_text,
    _gate_author_removals,
)
from ..review_prompts import ask_apply_choice, bulk_apply_with_review_gate
from ..summary import StepSummary, render_summary_panel

if TYPE_CHECKING:
    from ..ai import AIClient, CleanupSuggestion
    from ..db import CalibreDB


@app.command(
    epilog=(
        "Examples:\n\n"
        '  calibre-toolkit clean-titles "tag:booker"\n\n'
        '  calibre-toolkit clean-titles "series:Man Booker Prize" --limit 10 --dry-run\n\n'
        '  calibre-toolkit clean-titles "not custom_column_cleaned:true"\n'
    ),
)
def clean_titles(
    search: Annotated[
        str,
        typer.Argument(help='Calibre search string, e.g. "tag:booker" or "series:Booker"'),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", "-b", help="Books per AI request (default 10)"),
    ] = 10,
    auto_apply_high: Annotated[
        bool,
        typer.Option("--auto-apply-high", help="Apply high-confidence changes without prompting"),
    ] = False,
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-n", help="Cap the number of books processed (e.g. 50)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview proposed changes without writing to Calibre"),
    ] = False,
):
    """AI-assisted author and title cleanup."""
    cfg = _load_config(config)
    db = _make_db(cfg)
    ai = _make_ai(cfg, command_key="title_author")

    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — Author & Title Cleanup\n\n",
                ("Search: ", "dim"),
                (search, "bold"),
            ),
            border_style="cyan",
        )
    )

    mqg_column = cfg.get("mqg", {}).get("title_author_column")

    run_cleanup(
        db=db,
        ai=ai,
        search_query=search,
        batch_size=batch_size,
        auto_apply_high=auto_apply_high,
        mqg_column=mqg_column,
        limit=limit,
        dry_run=dry_run,
        apply_confirm_threshold=_apply_confirm_threshold(cfg),
        confirm_above_usd=_confirm_above_usd(cfg),
    )


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
    confirm_above_usd: float = 1.0,
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

    budget_guardrail(
        usage_step="title_author", n_books=len(books), model=ai.model,
        threshold=confirm_above_usd,
    )

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
        choice = ask_apply_choice(
            console,
            "[bold]Apply changes?[/bold]  \\[a]ll / \\[h]igh-only / \\[r]eview / \\[s]kip",
            choices=["all", "high-only", "review", "skip"],
            default="review",
        )
        if choice == "skip":
            console.print("[dim]No changes applied.[/dim]")
            raise typer.Exit()
        elif choice == "all":
            # Author removals are the v1.8 data-corruption guard: detection
            # (removes_author, the low-confidence cap) lives in
            # modules/authors.py; the helper owns the routing that keeps them
            # out of every bulk-apply path.
            a, _ = bulk_apply_with_review_gate(
                changes,
                console=console,
                apply_confirm_threshold=apply_confirm_threshold,
                apply_batch=lambda s: _apply_suggestions(db, s),
                review=lambda s: (_prompt_and_apply(db, s), []),
                is_review_only=lambda s: s.removes_author,
                gate_notice=lambda n: (
                    f"\n[yellow]{n} author-removal change(s) are never "
                    "bulk-applied — review each:[/yellow]\n"
                ),
                cancel_message="[dim]Bulk apply cancelled. No changes applied.[/dim]",
            )
            applied_ids += a
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
        db.mark_mqg_complete(book_ids, mqg_column, audit_step="clean-titles")
    console.print(
        f"[dim]Marked {len(book_ids)} books as complete in [bold]{mqg_column}[/bold].[/dim]"
    )
