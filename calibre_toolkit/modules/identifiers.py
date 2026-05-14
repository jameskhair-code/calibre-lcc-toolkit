"""
MQG-02 Identifier Enrichment module.
Orchestrates: fetch → lookup → display review table → confirm → apply.
"""

from __future__ import annotations

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

    @property
    def any_new(self) -> bool:
        return bool(self.new_identifiers)

    @property
    def author_display(self) -> str:
        return " & ".join(self.authors)


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


def _build_review_table(suggestions: list[IdentifierSuggestion]) -> Table:
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
    sufficient_types: list[str] | None = None,
    force_lookup: bool = False,
) -> None:
    """Full MQG-02 identifier enrichment flow for a given Calibre search string."""

    if sufficient_types is None:
        sufficient_types = ["isbn"]

    # ── 0. Probe binary ───────────────────────────────────────────────────────
    probe_error = fetcher.probe()
    if probe_error:
        console.print(Panel(probe_error, title="[red]fetch-ebook-metadata not available[/red]", border_style="red"))
        raise typer.Exit(1)

    # ── 1. Fetch books ────────────────────────────────────────────────────────
    try:
        with console.status(f"[cyan]Searching library:[/] {search_query}"):
            books = db.search(search_query)
    except RuntimeError as e:
        console.print(Panel(str(e), title="[red]Cannot access library[/red]", border_style="red"))
        raise typer.Exit(1)

    if not books:
        console.print("[yellow]No books matched that search. Nothing to do.[/yellow]")
        raise typer.Exit()

    console.print(f"\n[bold]Found [green]{len(books)}[/green] books.[/bold]")

    # ── 2. Lookup identifiers ─────────────────────────────────────────────────
    suggestions: list[IdentifierSuggestion] = []

    for idx, book in enumerate(books, 1):
        current = db.get_identifiers(book.id)

        if not force_lookup and _is_sufficient(current, sufficient_types):
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

    if failed:
        for s in failed:
            console.print(
                f"  [red]✗[/red] [dim]{s.title[:60]}[/dim] — "
                f"[yellow]{s.lookup_error}[/yellow]"
            )
        console.print()

    already_sufficient_ids = [s.book_id for s in already_sufficient]

    if not has_new:
        console.print("[green]Nothing new to add — no changes needed.[/green]")
        _mark_complete(db, mqg_column, already_sufficient_ids, label="already-sufficient")
        raise typer.Exit()

    # ── 4. Review table ───────────────────────────────────────────────────────
    table = _build_review_table(has_new)
    console.print(table)
    console.print(
        "\n[dim]Legend: [green]●[/green] High confidence (ISBN lookup)  "
        "[red]○[/red] Low confidence (title/author lookup — verify before accepting)[/dim]\n"
    )

    # ── 5. Apply options ──────────────────────────────────────────────────────
    high      = [s for s in has_new if s.confidence == "high"]
    low       = [s for s in has_new if s.confidence != "high"]
    applied_ids: list[int] = []

    if auto_apply_high and high:
        console.print(
            f"[bold]--auto-apply-high[/bold]: applying [green]{len(high)}[/green] "
            "high-confidence enrichments automatically.\n"
        )
        applied_ids += _apply_suggestions(db, high)
        if low:
            console.print(
                f"\n[yellow]{len(low)}[/yellow] low-confidence enrichments require your decision:\n"
            )
            applied_ids += _prompt_and_apply(db, low)
    else:
        choice = Prompt.ask(
            "[bold]Apply enrichments?[/bold]",
            choices=["all", "high-only", "review", "skip"],
            default="review",
            show_choices=True,
        )
        if choice == "skip":
            console.print("[dim]No changes applied.[/dim]")
            _mark_complete(db, mqg_column, already_sufficient_ids, label="already-sufficient")
            raise typer.Exit()
        elif choice == "all":
            applied_ids += _apply_suggestions(db, has_new)
        elif choice == "high-only":
            if high:
                applied_ids += _apply_suggestions(db, high)
                if low:
                    console.print(
                        f"\n[yellow]{len(low)}[/yellow] low-confidence enrichments skipped. "
                        "Run again to review them."
                    )
            else:
                console.print("[dim]No high-confidence enrichments to apply.[/dim]")
        elif choice == "review":
            applied_ids += _prompt_and_apply(db, has_new)

    # ── 6. Mark MQG complete ─────────────────────────────────────────────────
    # Only mark complete if the book now has ALL sufficient_types.
    # Books that got partial enrichment stay in the queue for another run.
    applied_map = {s.book_id: s for s in has_new}
    now_complete: list[int] = []
    still_incomplete: list[int] = []
    for book_id in applied_ids:
        s = applied_map[book_id]
        final_ids = {**s.current_identifiers, **s.new_identifiers}
        if _is_sufficient(final_ids, sufficient_types):
            now_complete.append(book_id)
        else:
            missing = [t for t in sufficient_types if t not in final_ids]
            still_incomplete.append(book_id)
            console.print(
                f"[dim]Book {book_id} ({s.title[:50]}): "
                f"still missing {', '.join(missing)} — will reappear on next run.[/dim]"
            )

    _mark_complete(db, mqg_column, already_sufficient_ids + now_complete, label="complete")
    console.print("\n[bold green]Done![/bold green]")


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


def _prompt_and_apply(db: CalibreDB, suggestions: list[IdentifierSuggestion]) -> list[int]:
    to_apply: list[IdentifierSuggestion] = []

    for s in suggestions:
        console.rule(f"[bold]Book {s.book_id}[/bold]")
        icon, style = _confidence_style(s.confidence)
        console.print(f"  {s.title}")
        console.print(f"  [dim]{s.author_display}[/dim]")
        console.print(f"  Confidence: [{style}]{icon} {s.confidence}[/{style}]")
        if s.current_identifiers:
            console.print(f"  Currently has: [dim]{', '.join(s.current_identifiers.keys())}[/dim]")
        for k, v in s.new_identifiers.items():
            console.print(f"  [green]+[/green] {k}: {v}")

        choice = Prompt.ask("  Action", choices=["y", "n"], default="y",
                            show_choices=True, show_default=True)
        if choice == "y":
            to_apply.append(s)

    if to_apply:
        return _apply_suggestions(db, to_apply)
    console.print("[dim]No enrichments applied.[/dim]")
    return []


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
