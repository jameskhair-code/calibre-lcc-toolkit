"""
MQG-02 Identifier Enrichment module.
Orchestrates: fetch → lookup → display review table → confirm → apply.
"""

from __future__ import annotations

import re
import typer
from dataclasses import dataclass, field
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.prompt import Prompt

from ..db import CalibreDB, Book
from ..fetcher import IdentifierFetcher, IDENTIFIER_TYPES


console = Console()

# ── Title match classification ────────────────────────────────────────────────

# Suffixes that are generic publication noise — same book, different marketing copy
_GENERIC_SUBTITLE_RE = re.compile(
    r":\s*(a|an|the)\s+"
    r"(novel|memoir|story|thriller|mystery|romance|biography|history|narrative|"
    r"tale|journey|collection|stories|poems|play|drama|comedy|novella|account|"
    r"chronicle|true\s+story|life|portrait)\s*$",
    re.IGNORECASE,
)

# Book club branding — typically a different print run / ISBN, not the original edition
_BOOK_CLUB_RE = re.compile(
    r"\b(oprah|reese|gma|book\s*club)\b"
    r"|\(.*book\s+club.*\)",
    re.IGNORECASE,
)

# Tie-in / adapted editions — not the original trade edition
_TIE_IN_RE = re.compile(
    r"\b(movie|film|tv|television|screen)\s*(tie[-\s]in|edition|version|adaptation)\b"
    r"|\(movie\s+tie[-\s]?in\)|\(film\s+tie[-\s]?in\)",
    re.IGNORECASE,
)


def _classify_title_match(calibre_title: str, returned_title: str) -> str:
    """Classify how the returned title relates to the Calibre title.

    Returns one of:
      "match"            — effectively the same title
      "generic_subtitle" — returned adds only generic publication noise (': A Novel')
      "book_club"        — returned has book club branding (likely different ISBN)
      "tie_in"           — returned has tie-in/movie marker (likely different ISBN)
      "mismatch"         — other meaningful difference — verify edition
    """
    if not returned_title:
        return "match"

    cal = calibre_title.strip()
    ret = returned_title.strip()

    if cal.lower() == ret.lower():
        return "match"

    # Check for specific edition flags before anything else
    if _BOOK_CLUB_RE.search(ret):
        return "book_club"
    if _TIE_IN_RE.search(ret):
        return "tie_in"

    # Strip generic subtitle from returned title and re-compare
    ret_stripped = _GENERIC_SUBTITLE_RE.sub("", ret).strip()
    if cal.lower() == ret_stripped.lower():
        return "generic_subtitle"

    # Calibre title is a clean prefix of the returned title (subtitle added)
    if ret_stripped.lower().startswith(cal.lower() + ":") or ret_stripped.lower() == cal.lower():
        return "generic_subtitle"

    return "mismatch"


# Labels and styles for each match class
_MATCH_CLASS_DISPLAY = {
    "match":            ("↳ matches",               "dim green",  ""),
    "generic_subtitle": ("↳ subtitle noise only",   "dim green",  ""),
    "book_club":        ("↳ book club edition",      "red",        " — likely different ISBN"),
    "tie_in":           ("↳ tie-in edition",         "red",        " — likely different ISBN"),
    "mismatch":         ("↳ title differs",          "yellow",     " — verify edition"),
}


@dataclass
class IdentifierSuggestion:
    book_id: int
    title: str
    authors: list[str]
    current_identifiers: dict[str, str]
    found_identifiers: dict[str, str]
    new_identifiers: dict[str, str]        # found - current
    lookup_method: str                     # "isbn" | "title_author"
    confidence: str                        # "high" | "low"
    lookup_attempted: bool
    lookup_error: str | None = None
    already_sufficient: bool = False
    returned_title: str = ""              # title returned by the lookup service
    returned_authors: list[str] = field(default_factory=list)

    @property
    def any_new(self) -> bool:
        return bool(self.new_identifiers)

    @property
    def author_display(self) -> str:
        return " & ".join(self.authors)

    @property
    def title_match_class(self) -> str:
        return _classify_title_match(self.title, self.returned_title)

    @property
    def returned_title_differs(self) -> bool:
        return self.title_match_class not in ("match", "generic_subtitle")


def _is_sufficient(identifiers: dict[str, str], required: list[str]) -> bool:
    """True only when ALL required types are present — ensures multirun enrichment."""
    return all(t in identifiers for t in required)


def _confidence_style(confidence: str) -> tuple[str, str]:
    return {"high": ("●", "green"), "low": ("○", "red")}.get(confidence, ("—", "dim"))


def _ids_display(identifiers: dict[str, str], highlight_keys: set[str] | None = None) -> Text:
    t = Text()
    for i, (k, v) in enumerate(identifiers.items()):
        if i:
            t.append("  ")
        style = "green bold" if highlight_keys and k in highlight_keys else "dim"
        t.append(f"{k}:", style="dim")
        t.append(v, style=style)
    return t


def _build_review_table(
    suggestions: list[IdentifierSuggestion],
    show_returned_title: bool = False,
) -> Table:
    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4, no_wrap=True)
    table.add_column("Conf", width=5, no_wrap=True)
    table.add_column("Book", ratio=4)
    table.add_column("Current IDs", ratio=3)
    table.add_column("New IDs Found", ratio=4)
    table.add_column("Method", width=13, no_wrap=True)

    for i, s in enumerate(suggestions, 1):
        icon, style = _confidence_style(s.confidence)
        conf_text = Text(icon, style=style)

        book_text = Text()
        book_text.append(s.title)
        book_text.append(f"\n{s.author_display}", style="dim")
        if show_returned_title and s.returned_title:
            mc = s.title_match_class
            label, style, note = _MATCH_CLASS_DISPLAY[mc]
            if mc in ("match", "generic_subtitle"):
                book_text.append(f"\n{label}", style=style)
            else:
                book_text.append(f"\n{label}: ", style=style)
                book_text.append(s.returned_title, style=f"{style} italic")
                if note:
                    book_text.append(note, style=f"{style} bold")

        current_text = Text()
        if s.current_identifiers:
            current_text.append("  ".join(s.current_identifiers.keys()), style="dim")
        else:
            current_text.append("(none)", style="dim italic")

        if s.lookup_error:
            new_text = Text(f"[{s.lookup_error}]", style="dim italic")
            method_text = Text("—", style="dim")
        else:
            new_text = _ids_display(s.new_identifiers, highlight_keys=set(s.new_identifiers))
            if not s.new_identifiers:
                new_text = Text("(nothing new)", style="dim italic")
            method_text = Text(s.lookup_method.replace("_", "/"), style="dim")

        table.add_row(str(i), conf_text, book_text, current_text, new_text, method_text)

    return table


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
    suggestions: list[IdentifierSuggestion] = []

    for idx, book in enumerate(books, 1):
        current = db.get_identifiers(book.id)

        if not force_lookup and _is_sufficient(current, sufficient_types) and _is_sufficient(current, mqg_complete_requires):
            suggestions.append(IdentifierSuggestion(
                book_id=book.id,
                title=book.title,
                authors=book.authors,
                current_identifiers=current,
                found_identifiers={},
                new_identifiers={},
                lookup_method="",
                confidence="high",
                lookup_attempted=False,
                already_sufficient=True,
            ))
            continue

        isbn = current.get("isbn")
        with console.status(
            f"[cyan]Looking up [{idx}/{len(books)}]:[/] {book.title[:60]}"
        ):
            result = fetcher.fetch(isbn=isbn, title=book.title, authors=book.authors)

        new_ids = {k: v for k, v in result.identifiers.items() if k not in current}

        suggestions.append(IdentifierSuggestion(
            book_id=book.id,
            title=book.title,
            authors=book.authors,
            current_identifiers=current,
            found_identifiers=result.identifiers,
            new_identifiers=new_ids,
            lookup_method=result.lookup_method,
            confidence=result.confidence,
            lookup_attempted=True,
            lookup_error=result.error,
            already_sufficient=False,
            returned_title=result.title,
            returned_authors=result.authors,
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
            choice_high = Prompt.ask(
                f"\n[bold]Tier 1:[/bold] Apply {len(high)} high-confidence enrichment{'s' if len(high) != 1 else ''}?",
                choices=["all", "review", "skip"],
                default="all",
                show_choices=True,
            )
            if choice_high == "all":
                applied_ids += _apply_suggestions(db, high)
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
        low_choice = Prompt.ask(
            "[bold]Tier 2:[/bold] Apply low-confidence enrichments?",
            choices=["all", "review", "skip"],
            default="review",
            show_choices=True,
        )
        if low_choice == "all":
            applied_ids += _apply_suggestions(db, low)
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

    total_enriched = len(applied_ids)
    total_complete = len(already_mqg_complete) + len(now_complete)
    total_manual = len(needs_manual) + len(manually_declined)
    console.print(
        f"\n[bold green]Done![/bold green] "
        f"[green]{total_enriched}[/green] enriched, "
        f"[green]{total_complete}[/green] marked MQG-02 complete"
        + (f", [yellow]{total_manual}[/yellow] flagged for manual review" if total_manual else "")
        + (f", [dim]{len(all_needs_ratings)} pending ratings[/dim]" if all_needs_ratings else "")
        + "."
    )


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


def run_unflag_manual(
    db: CalibreDB,
    search_query: str,
    mqg_manual_column: str,
    auto_apply: bool = False,
) -> None:
    """Clear the mqg_identifiers_manual flag for books matching search_query."""
    try:
        with console.status(f"[cyan]Searching:[/] {search_query}"):
            books = db.search(search_query)
    except RuntimeError as e:
        console.print(Panel(str(e), title="[red]Cannot access library[/red]", border_style="red"))
        raise typer.Exit(1)

    if not books:
        console.print("[yellow]No books matched that search.[/yellow]")
        raise typer.Exit()

    # Filter to only those actually flagged
    flagged: list[Book] = []
    with console.status("Checking manual flags…"):
        for book in books:
            ids = db.get_identifiers(book.id)  # we use a separate check via custom cols
            flagged.append(book)  # include all — calibredb will simply set false

    console.print(
        f"\n[bold]Found [green]{len(books)}[/green] book(s) matching the search.[/bold]\n"
        f"Clearing [bold]{mqg_manual_column}[/bold] will re-queue them for the next enrichment run.\n"
    )

    if not auto_apply:
        choice = Prompt.ask(
            "Clear the manual flag for all matched books?",
            choices=["y", "n"],
            default="y",
            show_choices=True,
        )
        if choice != "y":
            console.print("[dim]No changes made.[/dim]")
            raise typer.Exit()

    cleared = 0
    errors = 0
    with console.status(f"Clearing flags for {len(books)} book(s)…"):
        for book in books:
            try:
                db.clear_mqg_flag(book.id, mqg_manual_column)
                cleared += 1
            except RuntimeError as e:
                console.print(f"[red]Error on book {book.id}: {e}[/red]")
                errors += 1

    console.print(
        f"[green]Cleared flag for {cleared} book(s).[/green]"
        + (f" [red]{errors} error(s).[/red]" if errors else "")
    )
    console.print("\n[bold green]Done![/bold green]")
