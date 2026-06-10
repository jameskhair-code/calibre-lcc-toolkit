"""comments-enrich — MQG-04 AI comments / description enrichment.

Handler + orchestration (read details → AI generate → review → confirm →
write). Pure domain helpers (section labels, score styling, the review-table
builder) live in `modules/comments.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Annotated, TYPE_CHECKING

import typer
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.text import Text
from rich.prompt import Prompt

from datetime import datetime
from time import monotonic

from ._common import (
    app, console, DEFAULT_CONFIG_PATH,
    _load_config, _make_db, _make_ai, _apply_confirm_threshold,
)
from ..coherence import check_comments_coherence
from ..logging_config import audit_log
from ..modules.comments import (
    _CONF_DISPLAY,
    _SECTION_LABELS,
    _build_review_table,
    _score_style,
    _word_count,
)
from ..review_prompts import apply_tier
from ..summary import StepSummary, render_summary_panel

if TYPE_CHECKING:
    from ..ai import AIClient, CommentsSuggestion
    from ..db import CalibreDB


@app.command(
    epilog=(
        "Examples:\n\n"
        '  calibre-toolkit comments-enrich "#mqg_lcc:true" --limit 5 --dry-run\n\n'
        '  calibre-toolkit comments-enrich "#mqg_lcc:true and not #mqg_comments:true"\n'
    ),
)
def comments_enrich(
    search: Annotated[
        str,
        typer.Argument(help='Calibre search string, e.g. "#mqg_lcc:true and not #mqg_comments:true"'),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", "-b", help="Books per AI request (default 5)"),
    ] = 5,
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-n", help="Cap total books processed in this run (for testing)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview proposed changes without writing to Calibre"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Include books previously flagged for manual review"),
    ] = False,
    ai_model: Annotated[
        Optional[str],
        typer.Option("--ai-model", help="Override AI model. Accepts an alias (fast / latest / legacy) or a literal model ID."),
    ] = None,
):
    """
    MQG-04: AI-assisted book comments / description enrichment.

    For each book the AI generates a structured comment following the rules in
    rules/comments.md (fiction vs. non-fiction handled differently) and a
    0–10 must-read score with a short rationale. Voice and angle follow
    rules/reader_profile.md.
    """
    cfg = _load_config(config)
    db = _make_db(cfg)
    ai = _make_ai(cfg, command_key="comments", model_override=ai_model)

    comments_cfg = cfg.get("comments", {})
    mqg_column         = comments_cfg.get("mqg_column")
    mqg_manual_column  = comments_cfg.get("mqg_manual_column")
    lcc_summary_column = comments_cfg.get("lcc_summary_column", "#lcc_summary")

    _base = cfg.get("ai", {})
    _effective_model = ai_model or {**_base, **_base.get("comments", {})}.get("model", "(default)")

    mode_label = "Dry Run" if dry_run else "Enrich"
    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                f" — MQG-04 Comments ({mode_label})\n\n",
                ("Search:  ", "dim"),
                (search, "bold"),
                ("\nModel:   ", "dim"),
                (_effective_model, "bold"),
            ),
            border_style="cyan",
        )
    )

    run_comments_enrichment(
        db=db,
        ai=ai,
        search_query=search,
        batch_size=batch_size,
        limit=limit,
        dry_run=dry_run,
        force=force,
        mqg_column=mqg_column,
        mqg_manual_column=mqg_manual_column,
        lcc_summary_column=lcc_summary_column,
        apply_confirm_threshold=_apply_confirm_threshold(cfg),
    )


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

    # Cross-step coherence warnings (item 16).
    if s.coherence_warnings:
        console.print("  [bold red]⚠ Cross-step coherence:[/bold red]")
        for w in s.coherence_warnings:
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
    apply_confirm_threshold: int = 20,
    book_ids: list[int] | None = None,
) -> None:
    """Full MQG-04 Comments enrichment flow for a Calibre search string.

    force=True bypasses the manual-skip exclusion so books previously
    flagged for manual review are still picked up.

    book_ids, when given, replaces the search: the explicit list is processed
    verbatim (re-grade path), bypassing the search-string manual filter. The
    caller owns the manual-flag decision.
    """
    _started_at = datetime.now()
    _t0 = monotonic()

    # ── 1. Resolve books ──────────────────────────────────────────────────────
    if book_ids is not None:
        books = db.search_by_ids(book_ids)
        if not books:
            console.print("[yellow]No matching books for the given ids.[/yellow]")
            raise typer.Exit()
        console.print(f"\n[bold]Re-grading [green]{len(books)}[/green] book(s).[/bold]")
    else:
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
    book_id_list = [b.id for b in books]
    with console.status("[cyan]Reading book details and existing comments…"):
        details_map = db.get_book_details_batch(book_id_list)

    # ── 3. Read LCC summaries as optional context ─────────────────────────────
    lcc_summary_map: dict[int, str] = {}
    if lcc_summary_column:
        with console.status("[cyan]Reading LCC summaries for context…"):
            lcc_summary_map = db.get_custom_column_batch([b.id for b in books], lcc_summary_column)

    # ── 4. AI generation ───────────────────────────────────────────────────────
    total_batches = (len(books) + batch_size - 1) // batch_size
    progress = Progress(
        SpinnerColumn(),
        TextColumn(
            f"[cyan]Generating comments for {len(books)} book(s) "
            f"(batches of {batch_size})"
        ),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )
    with progress:
        task = progress.add_task("comments", total=total_batches)
        try:
            suggestions = ai.suggest_comments(
                books, details_map, lcc_summary_map, batch_size=batch_size,
                progress_callback=lambda completed, total, failed: progress.update(
                    task, completed=completed
                ),
            )
        except RuntimeError as e:
            console.print(Panel(str(e), title="[red]AI generation failed[/red]", border_style="red"))
            raise typer.Exit(1)

    if not suggestions:
        console.print("[yellow]AI returned no suggestions.[/yellow]")
        raise typer.Exit(1)

    # Cross-step coherence check (item 16). For each suggestion, see if
    # the AI prose names a period the book is not currently tagged for.
    # The current tags come from the book's existing metadata; they may
    # change in a later tags-enrich run, but at write time these are
    # what's on the shelf.
    for s in suggestions:
        details = details_map.get(s.book_id)
        current_tags = details.tags if details else []
        s.coherence_warnings = check_comments_coherence(s.html, current_tags)

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
        console.print(render_summary_panel(
            StepSummary(
                step_label="comments-enrich",
                started_at=_started_at,
                elapsed_seconds=monotonic() - _t0,
                applied_high=len(high),
                applied_medium=len(medium),
                applied_low=len(low),
                word_count=_word_count(suggestions),
                usage=ai.usage,
            ),
            dry_run=True,
        ))
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

    for tier, label, default, on_skip in (
        (high,   f"\n[bold]Tier 1:[/bold] Apply {len(high)} high-confidence "
                 f"comment{'s' if len(high) != 1 else ''}?  \\[a]ll / \\[r]eview / \\[s]kip",
         "all", False),
        (medium, f"\n[bold yellow]Tier 2:[/bold yellow] Apply {len(medium)} medium-confidence "
                 f"comment{'s' if len(medium) != 1 else ''}?  \\[a]ll / \\[r]eview / \\[s]kip",
         "review", False),
        (low,    f"\n[bold red]Tier 3:[/bold red] Apply {len(low)} low-confidence "
                 f"comment{'s' if len(low) != 1 else ''}?  \\[a]ll / \\[r]eview / \\[s]kip",
         "skip", True),
    ):
        a, d = apply_tier(
            tier,
            console=console,
            prompt=label,
            default=default,
            apply_confirm_threshold=apply_confirm_threshold,
            apply_batch=lambda s: _apply_batch(db, s),
            review=lambda s: _prompt_and_apply(db, s),
            declined_on_skip=on_skip,
        )
        applied_ids += a
        declined += d

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

    applied_ids_set = set(applied_ids)
    applied_suggestions = [s for s in suggestions if s.book_id in applied_ids_set]
    flagged = len(manual_ids) if mqg_manual_column else 0
    declined_only = len(declined) if not mqg_manual_column else 0
    console.print(render_summary_panel(
        StepSummary(
            step_label="comments-enrich",
            started_at=_started_at,
            elapsed_seconds=monotonic() - _t0,
            applied_high=sum(1 for s in high if s.book_id in applied_ids_set),
            applied_medium=sum(1 for s in medium if s.book_id in applied_ids_set),
            applied_low=sum(1 for s in low if s.book_id in applied_ids_set),
            skipped_declined=declined_only,
            flagged_manual=flagged,
            word_count=_word_count(applied_suggestions),
            usage=ai.usage,
        ),
    ))


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
