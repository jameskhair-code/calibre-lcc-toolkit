"""clean-identifiers — scan and fix malformed identifiers.

Handler + orchestration (scan → review → apply). The cleanup rules
(`_analyze`), the dataclasses, and the table builder live in
`modules/clean_identifiers.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, TYPE_CHECKING

import typer
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt

from ._common import app, console, DEFAULT_CONFIG_PATH, _load_config, _make_db
from ..modules.clean_identifiers import BookCleanup, _analyze, _build_table

if TYPE_CHECKING:
    from ..db import CalibreDB


@app.command(
    epilog=(
        "Examples:\n\n"
        '  calibre-toolkit clean-identifiers "all"\n\n'
        '  calibre-toolkit clean-identifiers "#mqg_identifiers:true"\n'
    ),
)
def clean_identifiers(
    search: Annotated[
        str,
        typer.Argument(help='Calibre search string, e.g. "all" or "#mqg_identifiers:true"'),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    auto_apply: Annotated[
        bool,
        typer.Option("--auto-apply", help="Apply all fixes without prompting"),
    ] = False,
):
    """Scan and fix malformed identifiers (UUIDs, urnisbn/ format, empty values)."""
    cfg = _load_config(config)
    db = _make_db(cfg)

    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — Identifier Cleanup\n\n",
                ("Search: ", "dim"),
                (search, "bold"),
            ),
            border_style="cyan",
        )
    )

    run_clean_identifiers(db=db, search_query=search, auto_apply=auto_apply)


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
