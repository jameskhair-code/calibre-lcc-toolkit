"""tags-enrich — MQG-05 AI subject tag enrichment.

Handler + orchestration (read tags/LCC context → AI propose → review →
confirm → write). Pure domain helpers (the comments excerpt, the review-table
builder, the tag diff renderer) live in `modules/tags.py`.
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
)
from ..coherence import check_tags_coherence
from ..logging_config import audit_log
from ..modules.tags import _CONF_DISPLAY, _build_review_table, _excerpt_from_comments
from ..review_prompts import confirm_bulk_apply
from ..summary import StepSummary, render_summary_panel

if TYPE_CHECKING:
    from ..ai import AIClient, TagsSuggestion
    from ..db import CalibreDB


@app.command(
    epilog=(
        "Examples:\n\n"
        '  calibre-toolkit tags-enrich "#mqg_lcc:true" --limit 10 --dry-run\n\n'
        '  calibre-toolkit tags-enrich "#mqg_lcc:true and not #mqg_tags:true"\n'
    ),
)
def tags_enrich(
    search: Annotated[
        str,
        typer.Argument(help='Calibre search string, e.g. "#mqg_lcc:true and not #mqg_tags:true"'),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", "-b", help="Books per AI request (default 20)"),
    ] = 20,
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-n", help="Cap total books processed in this run"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview proposed changes without writing to Calibre"),
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
    MQG-05: AI-assisted subject tag enrichment.

    Generates 4–8 flat tags per book across four categories:
      • Form     — Novel, Biography, History, Nonfiction, etc. (controlled list)
      • Subject  — Military History, Cold War, Public Health, etc.
      • Period   — World War II, Cold War, Victorian Era, etc.
      • Geography — United States, Russia, Sub-Saharan Africa, etc.

    Proposed tags replace existing tags. Confidence tiers and review
    flow match the other MQG commands. LCC data (if present) is used
    as context for more accurate subject tagging.
    """
    cfg = _load_config(config)
    db = _make_db(cfg)
    ai = _make_ai(cfg, command_key="tags", provider_override=ai_provider, model_override=ai_model)

    tags_cfg  = cfg.get("tags",  {})
    lcc_cfg   = cfg.get("lcc",   {})
    mqg_column        = tags_cfg.get("mqg_column")
    mqg_manual_column = tags_cfg.get("mqg_manual_column")

    _base = cfg.get("ai", {})
    _effective_model = ai_model or {**_base, **_base.get("tags", {})}.get("model", "(default)")

    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — MQG-05 Tags Enrichment\n\n",
                ("Search:  ", "dim"),
                (search, "bold"),
                ("\nModel:   ", "dim"),
                (_effective_model, "bold"),
            ),
            border_style="cyan",
        )
    )

    run_tags_enrichment(
        db=db,
        ai=ai,
        search_query=search,
        batch_size=batch_size,
        limit=limit,
        dry_run=dry_run,
        mqg_column=mqg_column,
        mqg_manual_column=mqg_manual_column,
        lcc_summary_column=lcc_cfg.get("lcc_summary_column", "#lcc_summary"),
        lcc_secondary_column=lcc_cfg.get("secondary_class_column", "#lcc_secondary_class"),
        lcc_primary_column=lcc_cfg.get("primary_class_column", "#lcc_primary_class"),
        apply_confirm_threshold=_apply_confirm_threshold(cfg),
    )


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
    apply_confirm_threshold: int = 20,
    book_ids: list[int] | None = None,
) -> None:
    """Full MQG-05 Tags enrichment flow for a Calibre search string.

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

    # ── 2. Read current tags, LCC context, and existing comments ──────────────
    # Switched from get_tags_batch to get_book_details_batch so we can
    # also feed an existing-comments excerpt into the tags prompt
    # (item 16 — coherence signal). One round-trip, same query path.
    book_id_list = [b.id for b in books]
    with console.status("[cyan]Reading current tags, LCC context, and existing comments…"):
        details_map = db.get_book_details_batch(book_id_list)
        tags_map = {bid: details_map[bid].tags for bid in book_id_list}
        comments_excerpt_map = {
            bid: _excerpt_from_comments(details_map[bid].existing_comments)
            for bid in book_id_list
        }
        context_map: dict[int, dict[str, str]] = {bid: {} for bid in book_id_list}
        for col_key, col_label in [
            ("lcc_summary",        lcc_summary_column),
            ("lcc_secondary_class", lcc_secondary_column),
            ("lcc_primary_class",   lcc_primary_column),
        ]:
            if col_label:
                batch = db.get_custom_column_batch(book_id_list, col_label)
                for bid, val in batch.items():
                    context_map[bid][col_key] = val

    # ── 3. AI generation ───────────────────────────────────────────────────────
    with console.status(
        f"[cyan]Generating tags for {len(books)} book(s) "
        f"in batches of {batch_size}…[/cyan]"
    ):
        try:
            suggestions = ai.suggest_tags(
                books, tags_map, context_map,
                comments_excerpt_map=comments_excerpt_map,
                batch_size=batch_size,
            )
        except RuntimeError as e:
            console.print(Panel(str(e), title="[red]AI generation failed[/red]", border_style="red"))
            raise typer.Exit(1)

    # ── 3b. Cross-step coherence check (item 16) ─────────────────────────────
    for s in suggestions:
        excerpt = comments_excerpt_map.get(s.book_id, "")
        s.coherence_warnings = check_tags_coherence(s.proposed_tags, excerpt)

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
        console.print(render_summary_panel(
            StepSummary(
                step_label="tags-enrich",
                started_at=_started_at,
                elapsed_seconds=monotonic() - _t0,
                applied_high=len(high),
                applied_medium=len(medium),
                applied_low=len(low),
                usage=ai.usage,
            ),
            dry_run=True,
        ))
        return

    console.print(_build_review_table(suggestions))
    console.print(
        "\n[dim]Legend: [green]●[/green] high  [yellow]◐[/yellow] medium  [red]○[/red] low  "
        "│  [dim]dim[/dim] = kept  [bold green]+ green[/bold green] = added  "
        "[red]- red[/red] = removed[/dim]\n"
    )

    # ── 5. Apply ───────────────────────────────────────────────────────────────
    applied_ids: list[int] = []
    declined: list[TagsSuggestion] = []

    if high:
        console.print("[dim]Waiting for input…[/dim]")
        choice = Prompt.ask(
            f"\n[bold]Tier 1:[/bold] Apply {len(high)} high-confidence "
            f"tag set{'s' if len(high) != 1 else ''}?  \\[a]ll / \\[r]eview / \\[s]kip",
            choices=["all", "review", "skip", "a", "r", "s"], default="all", show_choices=False,
        )
        choice = {"a": "all", "r": "review", "s": "skip"}.get(choice, choice)
        if choice == "all":
            if confirm_bulk_apply(len(high), apply_confirm_threshold, console):
                applied_ids += _apply_batch(db, high)
            else:
                console.print("[dim]Bulk apply cancelled.[/dim]")
        elif choice == "review":
            a, d = _prompt_and_apply(db, high)
            applied_ids += a
            declined += d

    if medium:
        console.print("[dim]Waiting for input…[/dim]")
        choice = Prompt.ask(
            f"\n[bold yellow]Tier 2:[/bold yellow] Apply {len(medium)} medium-confidence "
            f"tag set{'s' if len(medium) != 1 else ''}?  \\[a]ll / \\[r]eview / \\[s]kip",
            choices=["all", "review", "skip", "a", "r", "s"], default="review", show_choices=False,
        )
        choice = {"a": "all", "r": "review", "s": "skip"}.get(choice, choice)
        if choice == "all":
            if confirm_bulk_apply(len(medium), apply_confirm_threshold, console):
                applied_ids += _apply_batch(db, medium)
            else:
                console.print("[dim]Bulk apply cancelled.[/dim]")
        elif choice == "review":
            a, d = _prompt_and_apply(db, medium)
            applied_ids += a
            declined += d

    if low:
        console.print("[dim]Waiting for input…[/dim]")
        choice = Prompt.ask(
            f"\n[bold red]Tier 3:[/bold red] Apply {len(low)} low-confidence "
            f"tag set{'s' if len(low) != 1 else ''}?  \\[a]ll / \\[r]eview / \\[s]kip",
            choices=["all", "review", "skip", "a", "r", "s"], default="skip", show_choices=False,
        )
        choice = {"a": "all", "r": "review", "s": "skip"}.get(choice, choice)
        if choice == "all":
            if confirm_bulk_apply(len(low), apply_confirm_threshold, console):
                applied_ids += _apply_batch(db, low)
            else:
                console.print("[dim]Bulk apply cancelled.[/dim]")
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

    applied_ids_set = set(applied_ids)
    flagged = len(manual_ids) if mqg_manual_column else 0
    declined_only = len(declined) if not mqg_manual_column else 0
    console.print(render_summary_panel(
        StepSummary(
            step_label="tags-enrich",
            started_at=_started_at,
            elapsed_seconds=monotonic() - _t0,
            applied_high=sum(1 for s in high if s.book_id in applied_ids_set),
            applied_medium=sum(1 for s in medium if s.book_id in applied_ids_set),
            applied_low=sum(1 for s in low if s.book_id in applied_ids_set),
            skipped_declined=declined_only,
            flagged_manual=flagged,
            usage=ai.usage,
        ),
    ))


def _apply_batch(db: CalibreDB, suggestions: list[TagsSuggestion]) -> list[int]:
    applied: list[int] = []
    for s in suggestions:
        with console.status(f"Writing tags for book {s.book_id}…"):
            try:
                db.apply_tags(s.book_id, s.proposed_tags)
                applied.append(s.book_id)
                audit_log(
                    book_id=s.book_id,
                    field="tags",
                    new_value=s.proposed_tags,
                    confidence=s.confidence,
                    source="ai",
                    step="tags-enrich",
                )
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
        if s.kept:
            console.print(f"  Kept:     [dim]{', '.join(s.kept)}[/dim]")
        if s.added:
            console.print(f"  Added:    [bold green]{', '.join(s.added)}[/bold green]")
        if s.removed:
            console.print(f"  Removed:  [red]{', '.join(s.removed)}[/red]")
        if s.notes:
            console.print(f"  [dim]{s.notes}[/dim]")
        if s.coherence_warnings:
            console.print("  [bold red]⚠ Coherence:[/bold red]")
            for w in s.coherence_warnings:
                console.print(f"    [red]- {w}[/red]")

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
