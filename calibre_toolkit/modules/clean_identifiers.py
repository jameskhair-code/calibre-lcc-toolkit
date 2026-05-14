"""
Identifier cleanup module.
Scans books for malformed identifiers and offers to fix them.

Phase 1 rules:
  - UUID values in any field → remove
  - urnisbn/<isbn> as identifier type → normalize to isbn:<isbn>
  - Empty identifier values → remove
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

        # Rule 1: UUID value in any field
        if _UUID_RE.match(id_value or ""):
            changes.append(IdentifierChange(
                action="remove",
                old_type=id_type,
                old_value=id_value,
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
                        old_value=id_value or "",
                        new_type="isbn",
                        new_value=isbn,
                        reason="URN-format ISBN — normalize to isbn",
                    ))
                else:
                    changes.append(IdentifierChange(
                        action="remove",
                        old_type=id_type,
                        old_value=id_value or "",
                        reason="URN-format ISBN (isbn already present — remove duplicate)",
                    ))
            continue

        # Rule 3: empty value
        if not id_value:
            changes.append(IdentifierChange(
                action="remove",
                old_type=id_type,
                old_value="",
                reason="Empty value",
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
            "\n[bold]Apply fixes?[/bold]",
            choices=["all", "review", "skip"],
            default="all",
            show_choices=True,
        )
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
