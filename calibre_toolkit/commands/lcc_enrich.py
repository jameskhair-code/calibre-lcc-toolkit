"""lcc-enrich — MQG-03 AI-assisted LCC enrichment.

Handler + orchestration (read current fields → catalog lookup → AI propose →
validate → review → confirm → apply). Pure domain logic (call-number parsing,
canonical-CSV validation, catalog lookup, the renderable builders) lives in
`modules/lcc.py`.
"""

from __future__ import annotations

import os
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
from ..logging_config import audit_log, get_logger
from ..modules.lcc import (
    _CATALOG_LOOKUP_TIMEOUT,
    _CONF_DISPLAY,
    _LCC_FIELDS,
    _apply_ai_summary_to_catalog_hits,
    _build_audit_table,
    _build_catalog_suggestion,
    _build_review_table,
    _build_source_breakdown_extras,
    _catalog_lookup_batch,
    _read_current,
    _truncate_ai_only_lcc,
    _validate,
)
from ..review_prompts import apply_tier
from ..services.book_description import fetch_descriptions_batch
from ..summary import StepSummary, render_summary_panel

if TYPE_CHECKING:
    from ..ai import AIClient, LccSuggestion
    from ..db import CalibreDB
    from ..modules.lcc import ValidatedSuggestion
    from ..services.book_description import BookDescription

_log = get_logger(__name__)


@app.command(
    epilog=(
        "Examples:\n\n"
        '  calibre-toolkit lcc-enrich "#mqg_identifiers:true and not #mqg_lcc:true"\n\n'
        '  calibre-toolkit lcc-enrich "tag:booker" --batch-size 5 --auto-apply-high\n'
    ),
)
def lcc_enrich(
    search: Annotated[
        str,
        typer.Argument(help='Calibre search string, e.g. "#mqg_identifiers:true and not #mqg_lcc:true"'),
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
        typer.Option("--auto-apply-high", help="Apply high-confidence enrichments without prompting"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Re-process books that already have all four LCC fields"),
    ] = False,
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-n", help="Cap total books processed in this run (for testing)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview proposed changes without writing to Calibre"),
    ] = False,
    ai_provider: Annotated[
        Optional[str],
        typer.Option("--ai-provider", help="Override AI provider for this run (e.g. openai, anthropic)"),
    ] = None,
    ai_model: Annotated[
        Optional[str],
        typer.Option("--ai-model", help="Override AI model. Accepts an alias (fast / latest / legacy) or a literal model ID."),
    ] = None,
):
    """
    MQG-03: AI-assisted Library of Congress Classification (LCC) enrichment.

    For each book, proposes:
      • lcc (call number)
      • lcc_primary_class (drop-down)
      • lcc_secondary_class (drop-down)
      • lcc_summary (one-sentence subject summary)

    Primary and secondary class are code-derived from the AI-proposed call
    number and validated against config/lcc-{primary,secondary}-canonical.csv.
    """
    cfg = _load_config(config)
    db = _make_db(cfg)
    ai = _make_ai(cfg, command_key="lcc", provider_override=ai_provider, model_override=ai_model)

    lcc_cfg = cfg.get("lcc", {})
    columns = {
        "lcc": lcc_cfg.get("lcc_column", "#lcc"),
        "lcc_primary_class": lcc_cfg.get("primary_class_column", "#lcc_primary_class"),
        "lcc_secondary_class": lcc_cfg.get("secondary_class_column", "#lcc_secondary_class"),
        "lcc_summary": lcc_cfg.get("lcc_summary_column", "#lcc_summary"),
    }
    mqg_column = cfg.get("mqg", {}).get("lcc_column")
    mqg_manual_column = cfg.get("mqg", {}).get("lcc_manual_column")

    _base = cfg.get("ai", {})
    _effective_model = ai_model or {**_base, **_base.get("lcc", {})}.get("model", "(default)")

    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — MQG-03 LCC Enrichment\n\n",
                ("Search:  ", "dim"),
                (search, "bold"),
                ("\nModel:   ", "dim"),
                (_effective_model, "bold"),
            ),
            border_style="cyan",
        )
    )

    catalog_cfg = cfg.get("catalog", {})
    # `description` block is optional; it falls back to `catalog`'s discipline
    # so existing config.json files keep working without edits.
    description_cfg = cfg.get("description", {})
    description_timeout = float(
        description_cfg.get(
            "request_timeout_seconds",
            catalog_cfg.get("request_timeout_seconds", 10.0),
        )
    )
    description_max_retries = int(
        description_cfg.get(
            "max_retries",
            catalog_cfg.get("max_retries", 3),
        )
    )
    # Google Books requires an API key; env var wins over config (so a user
    # can rotate the key without touching config.json). Empty string is
    # treated as "no key" — the service short-circuits to Open Library.
    google_books_api_key = (
        os.environ.get("GOOGLE_BOOKS_API_KEY")
        or description_cfg.get("google_books_api_key", "")
    ) or None
    run_lcc_enrichment(
        db=db,
        ai=ai,
        search_query=search,
        columns=columns,
        batch_size=batch_size,
        limit=limit,
        auto_apply_high=auto_apply_high,
        mqg_column=mqg_column,
        mqg_manual_column=mqg_manual_column,
        force=force,
        dry_run=dry_run,
        catalog_timeout=float(catalog_cfg.get("request_timeout_seconds", 10.0)),
        catalog_max_retries=int(catalog_cfg.get("max_retries", 3)),
        description_timeout=description_timeout,
        description_max_retries=description_max_retries,
        google_books_api_key=google_books_api_key,
        apply_confirm_threshold=_apply_confirm_threshold(cfg),
    )


# ── Audit display ─────────────────────────────────────────────────────────────

def _print_audit_summary(
    validated: list[ValidatedSuggestion],
    current_map: dict[int, dict[str, str]],
) -> None:
    total = len(validated)
    exact_match = 0
    diff_counts: dict[str, int] = {k: 0 for k in _LCC_FIELDS}

    for v in validated:
        current  = current_map.get(v.book_id, {})
        proposed = v.final_fields
        any_diff = False
        for key in _LCC_FIELDS:
            if (current.get(key) or "") != (proposed.get(key) or ""):
                diff_counts[key] += 1
                any_diff = True
        if not any_diff:
            exact_match += 1

    differ = total - exact_match

    console.print("\n[bold]── Audit Summary ──────────────────────────────[/bold]")
    console.print(f"  Total reviewed:    [bold]{total}[/bold]")
    console.print(f"  [green]Exact match:       {exact_match}[/green]  [dim](AI agrees with current values)[/dim]")
    console.print(f"  [yellow]Have differences:  {differ}[/yellow]  [dim](AI would write something different)[/dim]")
    if differ:
        console.print("\n  [dim]Differences by field:[/dim]")
        labels = {"lcc": "LCC call number", "lcc_primary_class": "Primary class",
                  "lcc_secondary_class": "Secondary class", "lcc_summary": "LCC summary"}
        for key, count in diff_counts.items():
            if count:
                console.print(f"    {labels[key]}: [yellow]{count}[/yellow] book(s)")
    console.print("\n[dim]Dry-run complete — no changes were written.[/dim]")


# ── Orchestration ─────────────────────────────────────────────────────────────

def run_lcc_enrichment(
    db: CalibreDB,
    ai: AIClient,
    search_query: str,
    columns: dict[str, str],
    batch_size: int = 10,
    limit: int | None = None,
    auto_apply_high: bool = False,
    mqg_column: str | None = None,
    mqg_manual_column: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    catalog_timeout: float = _CATALOG_LOOKUP_TIMEOUT,
    catalog_max_retries: int = 3,
    description_timeout: float = _CATALOG_LOOKUP_TIMEOUT,
    description_max_retries: int = 3,
    google_books_api_key: str | None = None,
    apply_confirm_threshold: int = 20,
    book_ids: list[int] | None = None,
) -> None:
    """Full MQG-03 LCC enrichment flow for a Calibre search string.

    columns maps logical field name → custom column label:
        {"lcc": "#lcc", "lcc_primary_class": "#lcc_primary_class", ...}
    force=True processes books that already have all four fields populated.

    book_ids, when given, replaces the search: the explicit list is processed
    verbatim (re-grade path). It bypasses the search-string manual filter and
    the already-populated skip — the caller is authoritative about which books
    to (re-)process and owns the manual-flag decision.
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
        # --force overrides the manual-skip exclusion: when re-running on
        # purpose, the user wants to see books they previously declined too.
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

    # ── 2. Read current LCC values ────────────────────────────────────────────
    book_id_list = [b.id for b in books]
    with console.status("[cyan]Reading current LCC fields…"):
        current_map = _read_current(db, book_id_list, columns)

    # Skip books already fully populated unless --force (re-grade processes the
    # explicit list regardless — that's the whole point).
    skipped = 0
    if not force and book_ids is None:
        before = len(books)
        already_populated = [b.id for b in books if all(current_map[b.id][k] for k in _LCC_FIELDS)]
        books = [b for b in books if not all(current_map[b.id][k] for k in _LCC_FIELDS)]
        skipped = before - len(books)
        if skipped:
            console.print(
                f"[dim]Skipping {skipped} book(s) — all four LCC fields already populated. "
                "Use --force to re-process them.[/dim]"
            )
            if mqg_column and already_populated:
                _mark_complete(db, mqg_column, already_populated, label="already-populated")
    if not books:
        console.print("[green]Nothing to do — every matched book is already fully populated.[/green]")
        raise typer.Exit()

    # ── 3a. LC catalog pre-lookup ─────────────────────────────────────────────
    with console.status(
        f"[cyan]Looking up {len(books)} book(s) in the LC catalog "
        "(LCCN → ISBN)…[/cyan]"
    ):
        catalog_hits, cat_stats = _catalog_lookup_batch(
            db, books,
            timeout=catalog_timeout,
            max_retries=catalog_max_retries,
        )

    catalog_suggestions: list[LccSuggestion] = []
    ai_books = []
    for b in books:
        hit = catalog_hits.get(b.id)
        if hit:
            catalog_suggestions.append(
                _build_catalog_suggestion(b, current_map[b.id], hit)
            )
        else:
            ai_books.append(b)

    # One-line diagnostic so misses are explainable rather than mysterious.
    # Two source paths remain after the v1.3 LC removal: direct OL ISBN
    # lookup and the OL edition cascade.
    source_parts: list[str] = []
    if cat_stats.ol_direct_hits:
        source_parts.append(f"{cat_stats.ol_direct_hits} direct OL ISBN")
    if cat_stats.ol_cascade_hits:
        source_parts.append(f"{cat_stats.ol_cascade_hits} via OL edition cascade")
    source_note = f" ({', '.join(source_parts)})" if source_parts else ""
    cat_breakdown = (
        f"[dim]Catalog lookup: {cat_stats.tried_lccn} tried by LCCN, "
        f"{cat_stats.tried_isbn} by ISBN, "
        f"{cat_stats.no_identifiers} had no usable identifier — "
        f"{cat_stats.hits} hit(s){source_note}.[/dim]"
    )
    if catalog_suggestions:
        console.print(
            f"[green]✓[/green] Catalog hits: [bold green]{len(catalog_suggestions)}[/bold green] "
            f"of {len(books)} — AI will only run on the remaining "
            f"[bold]{len(ai_books)}[/bold]."
        )
        console.print(cat_breakdown)
    else:
        console.print(
            f"[dim]No LC catalog hits — falling through to AI for all {len(books)} book(s).[/dim]"
        )
        console.print(cat_breakdown)

    # ── 3b. Pre-fetch publisher descriptions for every book with an ISBN ──────
    # Original purpose (item 11): give the AI an authoritative source to
    # summarise from, eliminating lcc_summary hallucination on obscure
    # books. v1.7 item 5 widens the audience: catalog-hit books also get
    # descriptions so the summary-only AI call can ground its prose.
    # Graceful degradation: any books without an ISBN, or whose
    # descriptions cannot be fetched, simply do not appear in
    # `description_map` and the relevant AI step falls back (AI → training
    # data; summary-only → template summary).
    description_map: dict[int, BookDescription] = {}
    isbn_by_book: dict[int, str] = {}
    for b in books:
        ids = db.get_identifiers(b.id)
        isbn = (
            ids.get("isbn")
            or ids.get("isbn13")
            or ids.get("isbn10")
            or ids.get("ISBN")
            or ""
        )
        if isbn:
            isbn_by_book[b.id] = isbn

    if isbn_by_book:
        with console.status(
            f"[cyan]Pre-fetching descriptions for {len(isbn_by_book)} book(s) "
            "(Google Books → Open Library)…[/cyan]"
        ):
            description_map = fetch_descriptions_batch(
                isbn_by_book,
                timeout=description_timeout,
                max_retries=description_max_retries,
                google_books_api_key=google_books_api_key,
            )
        sources: dict[str, int] = {}
        for d in description_map.values():
            sources[d.source] = sources.get(d.source, 0) + 1
        no_isbn = len(books) - len(isbn_by_book)
        missed = len(isbn_by_book) - len(description_map)
        src_breakdown = ", ".join(
            f"{n} via {name}" for name, n in sorted(sources.items())
        ) or "none"
        console.print(
            f"[dim]Descriptions: {len(description_map)}/{len(books)} fetched "
            f"({src_breakdown}); {missed} no description available; "
            f"{no_isbn} had no ISBN.[/dim]"
        )
    else:
        console.print(
            "[dim]No ISBNs available — skipping description pre-fetch; "
            "AI will fall back to training data; catalog-hit books "
            "keep template summaries.[/dim]"
        )

    # ── 3c. AI lookup for the remainder ───────────────────────────────────────
    ai_suggestions: list[LccSuggestion] = []
    if ai_books:
        total_batches = (len(ai_books) + batch_size - 1) // batch_size
        progress = Progress(
            SpinnerColumn(),
            TextColumn(
                f"[cyan]Generating LCC fields for {len(ai_books)} book(s) "
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
            task = progress.add_task("lcc", total=total_batches)
            try:
                ai_suggestions = ai.suggest_lcc(
                    ai_books, current_map, batch_size=batch_size,
                    description_map=description_map,
                    progress_callback=lambda completed, total, failed: progress.update(
                        task, completed=completed
                    ),
                )
            except RuntimeError as e:
                console.print(Panel(str(e), title="[red]AI lookup failed[/red]", border_style="red"))
                raise typer.Exit(1)

    # v1.7 item 6: truncate AI-only `lcc` to class letters + class number.
    # Catalog-sourced suggestions are not touched.
    _truncate_ai_only_lcc(ai_suggestions)

    # ── 3d. v1.7 item 5: AI-prose lcc_summary for catalog hits with descriptions ─
    # When a catalog hit gives us trustworthy lcc/primary/secondary AND we
    # have a pre-fetched description, run one extra small AI call to
    # replace the terse template summary with description-grounded prose.
    # Catalog class fields are unchanged; only the summary is rewritten.
    # Books without a description keep the template summary. AI failures
    # fall back silently to the template too.
    _apply_ai_summary_to_catalog_hits(
        ai, books, catalog_suggestions, description_map, batch_size,
    )

    suggestions = catalog_suggestions + ai_suggestions

    if not suggestions:
        console.print("[yellow]No suggestions produced (neither catalog nor AI).[/yellow]")
        raise typer.Exit(1)

    # ── 4. Validate ───────────────────────────────────────────────────────────
    validated = [_validate(s) for s in suggestions]

    # Group by confidence
    high = [v for v in validated if v.suggestion.confidence == "high"]
    medium = [v for v in validated if v.suggestion.confidence == "medium"]
    low = [v for v in validated if v.suggestion.confidence == "low"]

    warned = [v for v in validated if v.has_warnings]
    console.print(
        f"\n[bold]Results:[/bold] "
        f"[green]{len(high)} high[/green], "
        f"[yellow]{len(medium)} medium[/yellow], "
        f"[red]{len(low)} low[/red]"
        + (f" — [yellow]{len(warned)} with validation warnings[/yellow]" if warned else "")
        + "\n"
    )

    _LEGEND = (
        "[dim]Legend: [green]●[/green] high (catalog-confirmed)  "
        "[yellow]◐[/yellow] medium (catalog-consensus)  "
        "[red]○[/red] low (schedule-derived or ambiguous)\n"
        "        Pri/Sec shown are CODE-DERIVED from the call number; "
        "warnings flag where AI disagreed.[/dim]\n"
    )

    if high:
        console.print(f"[bold cyan]Tier 1 — High confidence[/bold cyan] [dim]({len(high)})[/dim]")
        console.print(_build_review_table(high))
    if medium:
        console.print(f"\n[bold yellow]Tier 2 — Medium confidence[/bold yellow] [dim]({len(medium)})[/dim]")
        console.print(_build_review_table(medium))
    if low:
        console.print(f"\n[bold red]Tier 3 — Low confidence[/bold red] [dim]({len(low)})[/dim]")
        console.print(_build_review_table(low))
    console.print(_LEGEND)

    # v1.7 item 7: source breakdown surfaced in the summary panel.
    # OL direct / OL cascade / AI-only as discrete extras rows.
    extras = _build_source_breakdown_extras(cat_stats, ai_suggestions)

    # ── 5. Apply (or dry-run) ─────────────────────────────────────────────────
    if dry_run:
        console.print("[bold cyan]── Dry-run: comparing AI proposals to current values ──[/bold cyan]\n")
        console.print(_build_audit_table(validated, current_map))
        _print_audit_summary(validated, current_map)
        console.print(render_summary_panel(
            StepSummary(
                step_label="lcc-enrich",
                started_at=_started_at,
                elapsed_seconds=monotonic() - _t0,
                applied_high=len(high),
                applied_medium=len(medium),
                applied_low=len(low),
                skipped_already_done=skipped,
                extras=extras,
                usage=ai.usage,
            ),
            dry_run=True,
        ))
        return

    applied_ids: list[int] = []
    declined: list[ValidatedSuggestion] = []

    if high and auto_apply_high:
        console.print(f"[bold]--auto-apply-high[/bold]: applying {len(high)} high-confidence enrichments.\n")
        applied_ids += _apply_batch(db, high, columns)
    else:
        a, d = apply_tier(
            high,
            console=console,
            prompt=f"\n[bold]Tier 1:[/bold] Apply {len(high)} high-confidence enrichment{'s' if len(high) != 1 else ''}?  \\[a]ll / \\[r]eview / \\[s]kip",
            default="all",
            apply_confirm_threshold=apply_confirm_threshold,
            apply_batch=lambda v: _apply_batch(db, v, columns),
            review=lambda v: _prompt_and_apply(db, v, columns),
        )
        applied_ids += a; declined += d

    a, d = apply_tier(
        medium,
        console=console,
        prompt=f"\n[bold yellow]Tier 2:[/bold yellow] Apply {len(medium)} medium-confidence enrichment{'s' if len(medium) != 1 else ''}?  \\[a]ll / \\[r]eview / \\[s]kip",
        default="review",
        apply_confirm_threshold=apply_confirm_threshold,
        apply_batch=lambda v: _apply_batch(db, v, columns),
        review=lambda v: _prompt_and_apply(db, v, columns),
    )
    applied_ids += a; declined += d

    # Skipped low-confidence books are auto-flagged for manual curation.
    a, d = apply_tier(
        low,
        console=console,
        prompt=f"\n[bold red]Tier 3:[/bold red] Apply {len(low)} low-confidence enrichment{'s' if len(low) != 1 else ''}?  \\[a]ll / \\[r]eview / \\[s]kip",
        default="skip",
        apply_confirm_threshold=apply_confirm_threshold,
        apply_batch=lambda v: _apply_batch(db, v, columns),
        review=lambda v: _prompt_and_apply(db, v, columns),
        declined_on_skip=True,
    )
    applied_ids += a; declined += d

    # ── 6. Mark MQG / flag manual ─────────────────────────────────────────────
    # All applied books are marked MQG-03 complete — applied_ids already
    # reflects only what the user explicitly accepted at the review prompt.
    if mqg_column and applied_ids:
        _mark_complete(db, mqg_column, applied_ids, label="MQG-03")

    manual_ids = [v.book_id for v in declined]
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
            step_label="lcc-enrich",
            started_at=_started_at,
            elapsed_seconds=monotonic() - _t0,
            applied_high=sum(1 for v in high if v.book_id in applied_ids_set),
            applied_medium=sum(1 for v in medium if v.book_id in applied_ids_set),
            applied_low=sum(1 for v in low if v.book_id in applied_ids_set),
            skipped_already_done=skipped,
            skipped_declined=declined_only,
            flagged_manual=flagged,
            extras=extras,
            usage=ai.usage,
        ),
    ))


def _apply_suggestion(db: CalibreDB, v: ValidatedSuggestion, columns: dict[str, str]) -> None:
    fields = {}
    for field_name in _LCC_FIELDS:
        label = columns.get(field_name)
        if not label:
            continue
        fields[label] = v.final_fields[field_name]
    db.apply_custom_fields(v.book_id, fields)

    # Audit each field individually so a later analysis can grep by field.
    # `source` is the structural enum — a future audit can trust it; the
    # AI's free-text source string is preserved separately as `source_text`.
    structural_source = v.suggestion.source_authority
    source_text = v.suggestion.source or ""
    confidence = v.suggestion.confidence
    for label, value in fields.items():
        audit_log(
            book_id=v.book_id,
            field=label,
            new_value=value,
            confidence=confidence,
            source=structural_source,
            source_text=source_text,
            step="lcc-enrich",
        )
    _log.debug(
        "applied LCC suggestion for book %s (conf=%s, source=%s, prefix=%s)",
        v.book_id, confidence, structural_source, v.suggestion.attribution_prefix,
    )


def _apply_batch(
    db: CalibreDB,
    validated: list[ValidatedSuggestion],
    columns: dict[str, str],
) -> list[int]:
    applied: list[int] = []
    for v in validated:
        with console.status(f"Updating book {v.book_id}…"):
            try:
                _apply_suggestion(db, v, columns)
                applied.append(v.book_id)
            except RuntimeError as e:
                console.print(f"[red]Error on book {v.book_id}: {e}[/red]")
    console.print(f"[green]Applied {len(applied)}/{len(validated)} enrichments.[/green]")
    return applied


def _prompt_and_apply(
    db: CalibreDB,
    validated: list[ValidatedSuggestion],
    columns: dict[str, str],
) -> tuple[list[int], list[ValidatedSuggestion]]:
    to_apply: list[ValidatedSuggestion] = []
    declined: list[ValidatedSuggestion] = []
    for v in validated:
        s = v.suggestion
        console.rule(f"[bold]Book {v.book_id}[/bold]")
        console.print(f"  [bold]{s.title}[/bold]")
        console.print(f"  [dim]{s.authors_display}[/dim]")
        icon, style = _CONF_DISPLAY.get(s.confidence, ("—", "dim"))
        console.print(f"  Confidence: [{style}]{icon} {s.confidence}[/{style}]")
        console.print(
            f"  Source: [bold]{s.attribution_prefix}[/bold] "
            f"[dim italic]{s.source or '(no source text)'}[/dim italic]"
        )
        for field_name in _LCC_FIELDS:
            console.print(f"  [green]→[/green] {field_name}: {v.final_fields[field_name]}")
        if v.has_warnings:
            warns = []
            if v.primary_mismatch:   warns.append("primary mismatch")
            if v.secondary_mismatch: warns.append("secondary mismatch")
            if v.primary_invalid:    warns.append("primary not in canonical list")
            if v.secondary_invalid:  warns.append("secondary not in canonical list")
            console.print(f"  [yellow]Warnings: {'; '.join(warns)}[/yellow]")
        if s.notes:
            console.print(f"  [dim]Note: {s.notes}[/dim]")

        default = "n" if v.has_warnings or s.confidence == "low" else "y"
        choice = Prompt.ask("  Action", choices=["y", "n"], default=default,
                            show_choices=True, show_default=True)
        if choice == "y":
            to_apply.append(v)
        else:
            declined.append(v)
            console.print("  [dim]Declined — will be flagged for manual review.[/dim]")
    applied = _apply_batch(db, to_apply, columns) if to_apply else []
    return applied, declined


def _mark_complete(db: CalibreDB, mqg_column: str, book_ids: list[int], label: str) -> None:
    if not mqg_column or not book_ids:
        return
    with console.status(f"[cyan]Marking {len(book_ids)} books as {label} complete…"):
        db.mark_mqg_complete(book_ids, mqg_column)
    console.print(f"[dim]Marked {len(book_ids)} books complete in [bold]{mqg_column}[/bold].[/dim]")
