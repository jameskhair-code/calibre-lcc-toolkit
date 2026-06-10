"""enrich-identifiers — MQG-02 external identifier enrichment.

Handler + orchestration (probe → lookup → review → confirm → apply).
Pure domain helpers (title-match classification, the suggestion dataclass,
the parallel lookup pool, the review-table builder) live in
`modules/identifiers.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, TYPE_CHECKING

import typer
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt

from datetime import datetime
from time import monotonic

from ._common import (
    app, console, DEFAULT_CONFIG_PATH,
    _load_config, _make_db, _apply_confirm_threshold, _infer_fetch_path,
)
from ..logging_config import get_logger
from ..modules.identifiers import (
    _MATCH_CLASS_DISPLAY,
    IdentifierSuggestion,
    _build_review_table,
    _confidence_style,
    _is_sufficient,
    _parallel_lookup,
)
from ..review_prompts import confirm_bulk_apply
from ..summary import StepSummary, render_summary_panel

if TYPE_CHECKING:
    from ..db import CalibreDB, Book
    from ..fetcher import IdentifierFetcher

_log = get_logger(__name__)


@app.command(
    epilog=(
        "Examples:\n\n"
        '  calibre-toolkit enrich-identifiers "#metadata_queue:true"\n\n'
        '  calibre-toolkit enrich-identifiers "#mqg_title_author:true" --batch-size 10\n'
    ),
)
def enrich_identifiers(
    search: Annotated[
        str,
        typer.Argument(help='Calibre search string, e.g. "#metadata_queue:true"'),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", "-b", help="Books per run (each requires a live web lookup; default 20)"),
    ] = 20,
    auto_apply_high: Annotated[
        bool,
        typer.Option("--auto-apply-high", help="Apply high-confidence enrichments without prompting"),
    ] = False,
    force_lookup: Annotated[
        bool,
        typer.Option(
            "--force", "--force-lookup",
            help="Look up all books even if they already have a sufficient identifier "
                 "(--force-lookup is a deprecated alias)",
        ),
    ] = False,
):
    """
    MQG-02: Find and add external identifiers (ISBN, Goodreads, Amazon, etc.).

    Uses Calibre's own fetch-ebook-metadata tool to query configured metadata
    sources including Goodreads. Each book requires a live web lookup.
    Books that cannot be found are automatically flagged in the manual curation
    column (mqg.identifiers_manual_column in config.json).
    """
    from ..fetcher import IdentifierFetcher

    cfg = _load_config(config)
    db = _make_db(cfg)

    id_cfg = cfg.get("identifiers", {})
    fetch_path = _infer_fetch_path(cfg)
    fetcher_cfg = cfg.get("fetcher", {})
    timeout = fetcher_cfg.get(
        "request_timeout_seconds",
        id_cfg.get("lookup_timeout_seconds", 45),
    )
    max_retries = int(fetcher_cfg.get("max_retries", 2))
    sufficient_types = id_cfg.get("sufficient_types", ["isbn"])
    mqg_complete_requires = id_cfg.get("mqg_complete_requires", [])
    max_workers = int(id_cfg.get("max_workers", 4))
    mqg_column = cfg.get("mqg", {}).get("identifiers_column")
    mqg_manual_column = cfg.get("mqg", {}).get("identifiers_manual_column")

    fetcher = IdentifierFetcher(
        fetch_path=fetch_path,
        timeout=timeout,
        max_retries=max_retries,
    )

    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — MQG-02 Identifier Enrichment\n\n",
                ("Search: ", "dim"),
                (search, "bold"),
            ),
            border_style="cyan",
        )
    )

    run_enrichment(
        db=db,
        fetcher=fetcher,
        search_query=search,
        batch_size=batch_size,
        auto_apply_high=auto_apply_high,
        mqg_column=mqg_column,
        mqg_manual_column=mqg_manual_column,
        sufficient_types=sufficient_types,
        mqg_complete_requires=mqg_complete_requires,
        force_lookup=force_lookup,
        max_workers=max_workers,
        apply_confirm_threshold=_apply_confirm_threshold(cfg),
    )


def run_enrichment(
    db: CalibreDB,
    fetcher: IdentifierFetcher,
    search_query: str,
    batch_size: int = 20,
    auto_apply_high: bool = False,
    mqg_column: str | None = None,
    mqg_manual_column: str | None = None,
    sufficient_types: list[str] | None = None,
    mqg_complete_requires: list[str] | None = None,
    force_lookup: bool = False,
    max_workers: int = 4,
    apply_confirm_threshold: int = 20,
) -> None:
    """Full MQG-02 identifier enrichment flow for a given Calibre search string.

    sufficient_types      — gates whether to attempt a live lookup (book already
                           has enough data to skip).  Default: ["isbn"].
    mqg_complete_requires — additional types that must be present before MQG-02
                           is marked complete.  Default: [] (no extra gate).
                           Typical use: ["grrating", "grvotes"].
    """

    if sufficient_types is None:
        sufficient_types = ["isbn"]
    if mqg_complete_requires is None:
        mqg_complete_requires = []

    _started_at = datetime.now()
    _t0 = monotonic()

    # ── 0. Probe binary ───────────────────────────────────────────────────────
    probe_error = fetcher.probe()
    if probe_error:
        console.print(Panel(probe_error, title="[red]fetch-ebook-metadata not available[/red]", border_style="red"))
        raise typer.Exit(1)

    # ── 1. Fetch books ────────────────────────────────────────────────────────
    # Automatically exclude books already flagged for manual curation, unless
    # --force-lookup is set (caller is deliberately re-running).
    effective_query = (
        f"({search_query}) and not {mqg_manual_column}:true"
        if mqg_manual_column and not force_lookup else search_query
    )
    try:
        with console.status(f"[cyan]Searching library:[/] {search_query}"):
            books = db.search(effective_query)
            if mqg_manual_column and effective_query != search_query:
                all_books = db.search(search_query)
                skipped = len(all_books) - len(books)
            else:
                skipped = 0
    except RuntimeError as e:
        console.print(Panel(str(e), title="[red]Cannot access library[/red]", border_style="red"))
        raise typer.Exit(1)

    if not books:
        console.print("[yellow]No books matched that search. Nothing to do.[/yellow]")
        if skipped:
            console.print(
                f"[dim]({skipped} book(s) skipped — already flagged in "
                f"[bold]{mqg_manual_column}[/bold] for manual curation.)[/dim]"
            )
        raise typer.Exit()

    console.print(f"\n[bold]Found [green]{len(books)}[/green] books.[/bold]", end="")
    if skipped:
        console.print(
            f" [dim]({skipped} already in {mqg_manual_column} skipped.)[/dim]"
        )
    else:
        console.print()

    # ── 2. Lookup identifiers ─────────────────────────────────────────────────
    # Pre-classify books: those already sufficient skip the network entirely;
    # the rest go through the parallel lookup pool.
    suggestions: list[IdentifierSuggestion] = []
    pending: list[tuple[Book, dict[str, str]]] = []
    current_by_id: dict[int, dict[str, str]] = {}

    for book in books:
        current = db.get_identifiers(book.id)
        current_by_id[book.id] = current
        if (
            not force_lookup
            and _is_sufficient(current, sufficient_types)
            and _is_sufficient(current, mqg_complete_requires)
        ):
            continue
        pending.append((book, current))

    _log.debug(
        "MQG-02: %d total / %d already sufficient / %d to look up (workers=%d)",
        len(books), len(books) - len(pending), len(pending), max_workers,
    )

    if pending:
        lookup_results = _parallel_lookup(fetcher, pending, max_workers=max_workers)
    else:
        lookup_results = {}

    # Reassemble in input order so the review table matches the search result.
    for book in books:
        if book.id in lookup_results:
            suggestions.append(lookup_results[book.id])
        else:
            suggestions.append(IdentifierSuggestion(
                book_id=book.id,
                title=book.title,
                authors=book.authors,
                current_identifiers=current_by_id[book.id],
                found_identifiers={},
                new_identifiers={},
                lookup_method="",
                confidence="high",
                lookup_attempted=False,
                already_sufficient=True,
            ))

    # ── 3. Partition results ──────────────────────────────────────────────────
    already_sufficient = [s for s in suggestions if s.already_sufficient]
    has_new            = [s for s in suggestions if not s.already_sufficient and s.any_new]
    no_new_found       = [s for s in suggestions if not s.already_sufficient and not s.any_new and not s.lookup_error]
    failed             = [s for s in suggestions if s.lookup_error]

    console.print(
        f"\n[bold]Results:[/bold] "
        f"[green]{len(has_new)} enrichments available[/green], "
        f"[dim]{len(already_sufficient)} already sufficient, "
        f"{len(no_new_found)} no new found, "
        f"{len(failed)} lookup errors[/dim]\n"
    )

    # Auto-flag books that need manual attention: both hard errors and "nothing found"
    needs_manual = failed + no_new_found
    if needs_manual:
        if failed:
            console.print("[bold]Lookup errors:[/bold]")
            for s in failed:
                console.print(
                    f"  [red]✗[/red] [dim]{s.title[:60]}[/dim] — "
                    f"[yellow]{s.lookup_error}[/yellow]"
                )
        if no_new_found:
            console.print(
                f"[dim]{len(no_new_found)} book(s) looked up successfully but no new identifiers found.[/dim]"
            )

        needs_manual_ids = [s.book_id for s in needs_manual]
        if mqg_manual_column:
            console.print(
                f"\n[yellow]Auto-flagging {len(needs_manual_ids)} book(s)[/yellow] "
                f"in [bold]{mqg_manual_column}[/bold] for manual curation."
            )
            _mark_manual(db, mqg_manual_column, needs_manual_ids)
        else:
            console.print(
                f"\n[dim]{len(needs_manual_ids)} book(s) could not be enriched and were not flagged "
                "(set mqg.identifiers_manual_column in config.json to track them).[/dim]"
            )
        console.print()

    # Split already_sufficient by whether they also pass the completion gate
    already_mqg_complete   = [
        s for s in already_sufficient
        if _is_sufficient(s.current_identifiers, mqg_complete_requires)
    ]
    already_needs_ratings  = [
        s for s in already_sufficient
        if not _is_sufficient(s.current_identifiers, mqg_complete_requires)
    ]

    if not has_new:
        console.print("[green]Nothing new to add — no changes needed.[/green]")
        _mark_complete(db, mqg_column, [s.book_id for s in already_mqg_complete], label="already-sufficient")
        _report_needs_ratings(already_needs_ratings, mqg_complete_requires)
        raise typer.Exit()

    # ── 4. Partition by confidence & display tiered tables ───────────────────
    high = [s for s in has_new if s.confidence == "high"]
    low  = [s for s in has_new if s.confidence != "high"]

    _LEGEND = (
        "\n[dim]Legend: [green]●[/green] High confidence (ISBN lookup)  "
        "[red]○[/red] Low confidence (title/author lookup — verify before accepting)\n"
        "  [green]↳ green[/green] = title matches or subtitle noise only  "
        "[yellow]↳ yellow[/yellow] = edition differs — verify  "
        "[red]↳ red[/red] = book club / tie-in — defaults to N[/dim]\n"
    )

    if high:
        console.print(
            f"[bold cyan]Tier 1 — High confidence[/bold cyan] "
            f"[dim]({len(high)} book{'s' if len(high) != 1 else ''}, ISBN-verified)[/dim]"
        )
        console.print(_build_review_table(high, show_returned_title=True))

    if low:
        console.print(
            f"\n[bold yellow]Tier 2 — Low confidence[/bold yellow] "
            f"[dim]({len(low)} book{'s' if len(low) != 1 else ''}, title/author match — "
            "verify edition before accepting)[/dim]"
        )
        console.print(_build_review_table(low, show_returned_title=True))

    console.print(_LEGEND)

    # ── 5. Apply options ──────────────────────────────────────────────────────
    applied_ids: list[int] = []
    manually_declined: list[IdentifierSuggestion] = []

    # --- Tier 1: high confidence ---
    if high:
        if auto_apply_high:
            console.print(
                f"[bold]--auto-apply-high[/bold]: applying [green]{len(high)}[/green] "
                "high-confidence enrichments automatically.\n"
            )
            applied_ids += _apply_suggestions(db, high)
        else:
            console.print("[dim]Waiting for input…[/dim]")
            choice_high = Prompt.ask(
                f"\n[bold]Tier 1:[/bold] Apply {len(high)} high-confidence enrichment{'s' if len(high) != 1 else ''}?  \\[a]ll / \\[r]eview / \\[s]kip",
                choices=["all", "review", "skip", "a", "r", "s"],
                default="all",
                show_choices=False,
            )
            choice_high = {"a": "all", "r": "review", "s": "skip"}.get(choice_high, choice_high)
            if choice_high == "all":
                if confirm_bulk_apply(len(high), apply_confirm_threshold, console):
                    applied_ids += _apply_suggestions(db, high)
                else:
                    console.print("[dim]Bulk apply cancelled.[/dim]")
            elif choice_high == "review":
                ids, declined = _prompt_and_apply(db, high)
                applied_ids += ids
                manually_declined += declined
            # skip: do nothing

    # --- Tier 2: low confidence ---
    if low:
        console.print(
            f"\n[bold yellow]Tier 2:[/bold yellow] {len(low)} low-confidence enrichment{'s' if len(low) != 1 else ''} "
            "— title/author match (wrong ISBN will affect run 2):\n"
        )
        console.print("[dim]Waiting for input…[/dim]")
        low_choice = Prompt.ask(
            "[bold]Tier 2:[/bold] Apply low-confidence enrichments?  \\[a]ll / \\[r]eview / \\[s]kip",
            choices=["all", "review", "skip", "a", "r", "s"],
            default="review",
            show_choices=False,
        )
        low_choice = {"a": "all", "r": "review", "s": "skip"}.get(low_choice, low_choice)
        if low_choice == "all":
            if confirm_bulk_apply(len(low), apply_confirm_threshold, console):
                applied_ids += _apply_suggestions(db, low)
            else:
                console.print("[dim]Bulk apply cancelled.[/dim]")
        elif low_choice == "review":
            ids, declined = _prompt_and_apply(db, low)
            applied_ids += ids
            manually_declined += declined
        else:
            console.print(f"[dim]{len(low)} low-confidence enrichment(s) skipped. Run again to review.[/dim]")

    # ── 6. Mark MQG complete ─────────────────────────────────────────────────
    # Three-way split for enriched books:
    #   now_complete      — passes sufficient_types AND mqg_complete_requires → mark done
    #   phase1_complete   — missing sufficient_types (isbn/goodreads) → needs another run
    #   needs_ratings     — has sufficient_types but missing mqg_complete_requires → ratings retry
    applied_map = {s.book_id: s for s in has_new}
    now_complete: list[int] = []
    phase1_complete: list[IdentifierSuggestion] = []
    newly_needs_ratings: list[IdentifierSuggestion] = []

    for book_id in applied_ids:
        s = applied_map[book_id]
        final_ids = {**s.current_identifiers, **s.new_identifiers}
        if not _is_sufficient(final_ids, sufficient_types):
            phase1_complete.append(s)
        elif not _is_sufficient(final_ids, mqg_complete_requires):
            newly_needs_ratings.append(s)
        else:
            now_complete.append(book_id)

    if phase1_complete:
        sample_ids = {**phase1_complete[0].current_identifiers, **phase1_complete[0].new_identifiers}
        still_missing = [t for t in sufficient_types if t not in sample_ids]
        missing_str = ", ".join(f"[bold]{t}[/bold]" for t in still_missing)
        console.print(
            f"\n[dim]Phase 1 complete for [bold]{len(phase1_complete)}[/bold] book(s) — "
            f"still need {missing_str} to finish enrichment. "
            "Run again after confirming ISBNs to complete Phase 2.[/dim]"
        )

    # Report books that have sufficient IDs but still lack ratings
    all_needs_ratings = already_needs_ratings + newly_needs_ratings
    _report_needs_ratings(all_needs_ratings, mqg_complete_requires)

    # Flag manually declined books alongside lookup failures
    if manually_declined and mqg_manual_column:
        declined_ids = [s.book_id for s in manually_declined]
        console.print(
            f"\n[yellow]Flagging {len(declined_ids)} manually declined book(s)[/yellow] "
            f"in [bold]{mqg_manual_column}[/bold] for manual curation."
        )
        _mark_manual(db, mqg_manual_column, declined_ids)

    _mark_complete(
        db, mqg_column,
        [s.book_id for s in already_mqg_complete] + now_complete,
        label="complete",
    )

    total_manual = len(needs_manual) + len(manually_declined)
    applied_ids_set = set(applied_ids)
    applied_suggestions = [s for s in has_new if s.book_id in applied_ids_set]
    by_lookup_method: dict[str, int] = {}
    for s in applied_suggestions:
        key = s.lookup_method or "unknown"
        by_lookup_method[key] = by_lookup_method.get(key, 0) + 1

    extras: dict[str, dict[str, int]] = {}
    if by_lookup_method:
        extras["by_lookup_method"] = by_lookup_method

    console.print(render_summary_panel(
        StepSummary(
            step_label="enrich-identifiers",
            started_at=_started_at,
            elapsed_seconds=monotonic() - _t0,
            applied_high=sum(1 for s in high if s.book_id in applied_ids_set),
            applied_low=sum(1 for s in low if s.book_id in applied_ids_set),
            skipped_already_done=len(already_sufficient),
            flagged_manual=total_manual,
            pending_followup=len(all_needs_ratings),
            extras=extras,
        ),
    ))


def _apply_suggestions(db: CalibreDB, suggestions: list[IdentifierSuggestion]) -> list[int]:
    applied: list[int] = []
    for s in suggestions:
        with console.status(f"Updating book {s.book_id}…"):
            try:
                merged = {**s.current_identifiers, **s.new_identifiers}
                db.apply_identifiers(s.book_id, merged)
                applied.append(s.book_id)
            except RuntimeError as e:
                console.print(f"[red]Error on book {s.book_id}: {e}[/red]")
    console.print(f"[green]Applied {len(applied)}/{len(suggestions)} enrichments.[/green]")
    return applied


def _prompt_and_apply(
    db: CalibreDB,
    suggestions: list[IdentifierSuggestion],
) -> tuple[list[int], list[IdentifierSuggestion]]:
    """Step through suggestions one by one.

    Returns (applied_ids, declined_suggestions).
    Declined books are returned so the caller can flag them for manual curation.
    """
    to_apply: list[IdentifierSuggestion] = []
    declined: list[IdentifierSuggestion] = []

    for s in suggestions:
        console.rule(f"[bold]Book {s.book_id}[/bold]")
        icon, style = _confidence_style(s.confidence)
        console.print(f"  [bold]{s.title}[/bold]")
        console.print(f"  [dim]{s.author_display}[/dim]")
        if s.returned_title:
            mc = s.title_match_class
            _, rt_style, rt_note = _MATCH_CLASS_DISPLAY[mc]
            if mc in ("match", "generic_subtitle"):
                console.print(f"  [dim green]↳ Returned title matches.[/dim green]")
            else:
                console.print(
                    f"  [{rt_style}]↳ Returned title:[/{rt_style}] "
                    f"[{rt_style} italic]{s.returned_title}[/{rt_style} italic]"
                    + (f"  [{rt_style} bold]{rt_note}[/{rt_style} bold]" if rt_note else "")
                )
        console.print(f"  Confidence: [{style}]{icon} {s.confidence}[/{style}]")
        if s.current_identifiers:
            console.print(f"  Currently has: [dim]{', '.join(s.current_identifiers.keys())}[/dim]")
        for k, v in s.new_identifiers.items():
            console.print(f"  [green]+[/green] {k}: {v}")

        # Default to N for edition-specific flags — these usually need manual verification
        default_action = "n" if s.title_match_class in ("book_club", "tie_in") else "y"
        choice = Prompt.ask("  Action", choices=["y", "n"], default=default_action,
                            show_choices=True, show_default=True)
        if choice == "y":
            to_apply.append(s)
        else:
            declined.append(s)
            console.print("  [dim]Flagging for manual curation.[/dim]")

    applied = _apply_suggestions(db, to_apply) if to_apply else []
    if not to_apply:
        console.print("[dim]No enrichments applied.[/dim]")
    return applied, declined


def _report_needs_ratings(
    suggestions: list[IdentifierSuggestion],
    mqg_complete_requires: list[str],
) -> None:
    """Print a summary for books that are enriched but still missing the ratings gate."""
    if not suggestions or not mqg_complete_requires:
        return
    missing_types = ", ".join(f"[bold]{t}[/bold]" for t in mqg_complete_requires)
    console.print(
        f"\n[yellow]{len(suggestions)} book(s) are enriched but still missing {missing_types}.[/yellow]\n"
        "  These are [bold]not[/bold] marked MQG-02 complete yet.\n"
        "  Options:\n"
        "  [dim]• Run again — the next ISBN-based lookup may return the ratings.\n"
        "  • Run with [bold]--force-lookup[/bold] to force a fresh fetch for these books.\n"
        "  • Check and add grrating/grvotes manually in Calibre.[/dim]"
    )


def _mark_complete(
    db: CalibreDB,
    mqg_column: str | None,
    book_ids: list[int],
    label: str = "processed",
) -> None:
    if not mqg_column or not book_ids:
        return
    with console.status(f"[cyan]Marking {len(book_ids)} {label} books as MQG-02 complete…"):
        db.mark_mqg_complete(book_ids, mqg_column)
    console.print(
        f"[dim]Marked {len(book_ids)} books as complete in [bold]{mqg_column}[/bold].[/dim]"
    )


def _mark_manual(
    db: CalibreDB,
    mqg_manual_column: str,
    book_ids: list[int],
) -> None:
    if not book_ids:
        return
    with console.status(f"[cyan]Flagging {len(book_ids)} books for manual curation…"):
        db.mark_mqg_complete(book_ids, mqg_manual_column)
