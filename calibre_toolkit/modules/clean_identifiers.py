"""
Identifier cleanup module.
Scans books for malformed identifiers and offers to fix them.

Rules applied:
  - UUID values in any field → remove
  - urnisbn/<isbn> as identifier type → normalize to isbn:<isbn>
  - urnuuid* as identifier type (with or without slash) → remove
  - isbn10 / isbn13 / isbn-10 type names → normalize to isbn (or remove if isbn present)
  - ISBN or p-prefix embedded in type name (e.g. isbn9780007462520) → normalize to isbn
  - Bare ISBN-13 (978/979 prefix, 13 digits) stored as type name → normalize to isbn
  - Known junk/artifact/store types → remove
  - Hyphens/spaces in isbn values → strip
  - Whitespace-only or empty values → remove
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from ..db import CalibreDB, Book

console = Console()

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# ISBN embedded directly in type name, with optional isbn or p prefix
# Matches: isbn9780007462520, p9780299300234, p9781940941141
_ISBN_AS_TYPE_RE = re.compile(r"^(?:isbn|p)(\d{10}|\d{13})$", re.IGNORECASE)

# Bare ISBN-13 stored as type name (e.g. 9780061760358) — 978/979 prefix, 13 digits
_BARE_ISBN13_TYPE_RE = re.compile(r"^97[89]\d{10}$")

# Non-digit chars to strip from isbn values (hyphens and spaces)
_ISBN_NOISE_RE = re.compile(r"[-\s]")

# Non-standard type names that encode isbn
_ISBN_ALIASES = frozenset({"isbn10", "isbn13", "isbn-10"})

# Types to remove outright — store artifacts, defunct sites, URL noise, DRM keys
_REMOVE_TYPES = frozenset({
    # DRM / plugin artifacts
    "acs6", "epubbud", "notes_images", "revision", "ligmd5",
    # Typos / ambiguous
    "oasin",
    # URL/URI noise — import artifacts, not useful for lookup
    "url", "url2", "url3", "uri", "urn", "access_url", "ark",
    # Store identifiers not used in this library's workflow
    "ozon", "epl", "ilot", "guid", "amazon_uk", "sonybookid",
    # Retail store identifiers with very low coverage — not worth maintaining
    "asin", "kobo",
    # ISBN variants — normalize or remove in favour of isbn
    "eisbn", "ean",
    # LibraryThing — not used in this workflow
    "ltid",
    # Academic/archive identifiers not relevant to this collection
    "doi",
    # Specialist databases with negligible coverage in this library
    "isfdb", "isfdb-title", "lccn",
})


@dataclass
class IdentifierChange:
    action: str          # "remove" | "normalize"
    old_type: str
    old_value: str
    new_type: str | None = None
    new_value: str | None = None
    reason: str = ""


@dataclass
class BookCleanup:
    book_id: int
    title: str
    authors: list[str]
    changes: list[IdentifierChange]
    current_identifiers: dict[str, str]

    @property
    def author_display(self) -> str:
        return " & ".join(self.authors)

    def apply(self) -> dict[str, str]:
        result = dict(self.current_identifiers)
        for change in self.changes:
            result.pop(change.old_type, None)
            if change.action == "normalize" and change.new_type and change.new_value:
                result[change.new_type] = change.new_value
        return result


def _analyze(identifiers: dict[str, str]) -> list[IdentifierChange]:
    changes: list[IdentifierChange] = []

    for id_type, id_value in identifiers.items():
        raw_value = id_value or ""
        value = raw_value.strip()

        # Rule 1: UUID value in any field
        if _UUID_RE.match(value):
            changes.append(IdentifierChange(
                action="remove",
                old_type=id_type,
                old_value=raw_value,
                reason="UUID — not a valid external identifier",
            ))
            continue

        # Rule 2: urnisbn/<isbn> stored as the identifier type
        if id_type.startswith("urnisbn/"):
            isbn = id_type[8:]
            if isbn:
                if "isbn" not in identifiers:
                    changes.append(IdentifierChange(
                        action="normalize",
                        old_type=id_type,
                        old_value=value,
                        new_type="isbn",
                        new_value=isbn,
                        reason="URN-format ISBN — normalize to isbn",
                    ))
                else:
                    changes.append(IdentifierChange(
                        action="remove",
                        old_type=id_type,
                        old_value=value,
                        reason="URN-format ISBN (isbn already present — remove duplicate)",
                    ))
            continue

        # Rule 3: urnuuid* stored as type (with or without slash: urnuuid/, urnuuid0...)
        if id_type.startswith("urnuuid"):
            changes.append(IdentifierChange(
                action="remove",
                old_type=id_type,
                old_value=value,
                reason="URN UUID type — not a valid external identifier",
            ))
            continue

        # Rule 4: non-standard isbn alias types (isbn10, isbn13, isbn-10)
        if id_type in _ISBN_ALIASES:
            if "isbn" not in identifiers:
                changes.append(IdentifierChange(
                    action="normalize",
                    old_type=id_type,
                    old_value=value,
                    new_type="isbn",
                    new_value=value,
                    reason=f"Non-standard ISBN type '{id_type}' — normalize to isbn",
                ))
            else:
                changes.append(IdentifierChange(
                    action="remove",
                    old_type=id_type,
                    old_value=value,
                    reason=f"Non-standard ISBN type '{id_type}' (isbn already present — remove duplicate)",
                ))
            continue

        # Rule 5: ISBN embedded in type name (isbn9780007462520, p9780299300234)
        m = _ISBN_AS_TYPE_RE.match(id_type)
        if m:
            extracted = m.group(1)
            if "isbn" not in identifiers:
                changes.append(IdentifierChange(
                    action="normalize",
                    old_type=id_type,
                    old_value=value,
                    new_type="isbn",
                    new_value=extracted,
                    reason=f"ISBN embedded in type name — normalize to isbn:{extracted}",
                ))
            else:
                changes.append(IdentifierChange(
                    action="remove",
                    old_type=id_type,
                    old_value=value,
                    reason="ISBN embedded in type name (isbn already present — remove duplicate)",
                ))
            continue

        # Rule 6: bare ISBN-13 stored as type name (e.g. 9780061760358)
        if _BARE_ISBN13_TYPE_RE.match(id_type):
            if "isbn" not in identifiers:
                changes.append(IdentifierChange(
                    action="normalize",
                    old_type=id_type,
                    old_value=value,
                    new_type="isbn",
                    new_value=id_type,
                    reason=f"ISBN-13 stored as type name — normalize to isbn:{id_type}",
                ))
            else:
                changes.append(IdentifierChange(
                    action="remove",
                    old_type=id_type,
                    old_value=value,
                    reason="ISBN-13 stored as type name (isbn already present — remove duplicate)",
                ))
            continue

        # Rule 7: known junk / artifact / non-useful types
        if id_type in _REMOVE_TYPES:
            changes.append(IdentifierChange(
                action="remove",
                old_type=id_type,
                old_value=value,
                reason="Non-useful identifier type — library hygiene",
            ))
            continue

        # Rule 8: empty or whitespace-only value
        if not value:
            changes.append(IdentifierChange(
                action="remove",
                old_type=id_type,
                old_value=raw_value,
                reason="Whitespace-only value" if raw_value else "Empty value",
            ))
            continue

        # Rule 9: isbn value normalization — strip hyphens and spaces
        if id_type == "isbn":
            normalized = _ISBN_NOISE_RE.sub("", value)
            if normalized != value:
                changes.append(IdentifierChange(
                    action="normalize",
                    old_type="isbn",
                    old_value=value,
                    new_type="isbn",
                    new_value=normalized,
                    reason="Strip hyphens/spaces from ISBN value",
                ))
            continue

        # Rule 10: whitespace in value for any other type
        if value != raw_value:
            changes.append(IdentifierChange(
                action="normalize",
                old_type=id_type,
                old_value=raw_value,
                new_type=id_type,
                new_value=value,
                reason="Strip leading/trailing whitespace from value",
            ))

    return changes


def _build_table(cleanups: list[BookCleanup]) -> Table:
    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4, no_wrap=True)
    table.add_column("Book", ratio=3)
    table.add_column("Current identifier", ratio=3)
    table.add_column("Action", width=12, no_wrap=True)
    table.add_column("Result", ratio=3)

    row_num = 1
    for c in cleanups:
        for change in c.changes:
            book_text = Text()
            book_text.append(c.title[:50])
            book_text.append(f"\n{c.author_display[:40]}", style="dim")

            issue_text = Text()
            issue_text.append(f"{change.old_type}:", style="dim")
            val_display = change.old_value[:28] + ("…" if len(change.old_value) > 28 else "")
            issue_text.append(val_display, style="red")
            issue_text.append(f"\n{change.reason}", style="dim italic")

            if change.action == "remove":
                action_text = Text("remove", style="red")
                result_text = Text("—", style="dim")
            else:
                action_text = Text("normalize", style="yellow")
                result_text = Text(
                    f"{change.new_type}:{change.new_value}", style="green"
                )

            table.add_row(str(row_num), book_text, issue_text, action_text, result_text)
            row_num += 1

    return table


def run_clean_identifiers(
    db: CalibreDB,
    search_query: str,
    auto_apply: bool = False,
) -> None:
    try:
        with console.status(f"[cyan]Scanning:[/] {search_query}"):
            books = db.search(search_query)
    except RuntimeError as e:
        console.print(Panel(str(e), title="[red]Cannot access library[/red]", border_style="red"))
        raise typer.Exit(1)

    if not books:
        console.print("[yellow]No books matched that search.[/yellow]")
        raise typer.Exit()

    console.print(f"\n[bold]Scanning [green]{len(books)}[/green] books…[/bold]")

    cleanups: list[BookCleanup] = []
    for book in books:
        identifiers = db.get_identifiers(book.id)
        changes = _analyze(identifiers)
        if changes:
            cleanups.append(BookCleanup(
                book_id=book.id,
                title=book.title,
                authors=book.authors,
                changes=changes,
                current_identifiers=identifiers,
            ))

    if not cleanups:
        console.print("[green]No issues found — all identifiers look clean.[/green]")
        raise typer.Exit()

    total = sum(len(c.changes) for c in cleanups)
    console.print(
        f"\n[bold]Found [yellow]{total}[/yellow] issue{'s' if total != 1 else ''} "
        f"across [yellow]{len(cleanups)}[/yellow] book{'s' if len(cleanups) != 1 else ''}.[/bold]\n"
    )
    console.print(_build_table(cleanups))

    if auto_apply:
        console.print(f"\n[bold]--auto-apply:[/bold] applying all {total} fix(es).\n")
        _apply(db, cleanups)
    else:
        choice = Prompt.ask(
            "\n[bold]Apply fixes?[/bold]  \\[a]ll / \\[r]eview / \\[s]kip",
            choices=["all", "review", "skip", "a", "r", "s"],
            default="all",
            show_choices=False,
        )
        choice = {"a": "all", "r": "review", "s": "skip"}.get(choice, choice)
        if choice == "all":
            _apply(db, cleanups)
        elif choice == "review":
            _review_and_apply(db, cleanups)
        else:
            console.print("[dim]No changes applied.[/dim]")

    console.print("\n[bold green]Done![/bold green]")


def _apply(db: CalibreDB, cleanups: list[BookCleanup]) -> None:
    applied = 0
    for c in cleanups:
        try:
            db.apply_identifiers(c.book_id, c.apply())
            applied += len(c.changes)
        except RuntimeError as e:
            console.print(f"[red]Error on book {c.book_id}: {e}[/red]")
    console.print(f"[green]Applied {applied} fix(es) across {len(cleanups)} book(s).[/green]")


def _review_and_apply(db: CalibreDB, cleanups: list[BookCleanup]) -> None:
    to_apply: list[BookCleanup] = []
    for c in cleanups:
        console.rule(f"[bold]Book {c.book_id}[/bold]")
        console.print(f"  {c.title}")
        console.print(f"  [dim]{c.author_display}[/dim]")
        for change in c.changes:
            if change.action == "remove":
                console.print(
                    f"  [red]✗[/red] remove [dim]{change.old_type}:[/dim]"
                    f"{change.old_value[:40]}  [dim italic]({change.reason})[/dim italic]"
                )
            else:
                console.print(
                    f"  [yellow]→[/yellow] [dim]{change.old_type}[/dim] "
                    f"→ [green]{change.new_type}:{change.new_value}[/green]"
                    f"  [dim italic]({change.reason})[/dim italic]"
                )
        choice = Prompt.ask("  Apply?", choices=["y", "n"], default="y",
                            show_choices=True, show_default=True)
        if choice == "y":
            to_apply.append(c)

    if to_apply:
        _apply(db, to_apply)
    else:
        console.print("[dim]No fixes applied.[/dim]")
