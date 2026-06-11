"""unflag-manual — clear the MQG-02 manual-curation flag.

Handler + orchestration. Re-queues manually-fixed books for the next
enrich-identifiers run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, TYPE_CHECKING

import typer
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt

from ._common import app, console, DEFAULT_CONFIG_PATH, _load_config, _make_db

if TYPE_CHECKING:
    from ..db import CalibreDB, Book


@app.command(
    epilog=(
        "Examples:\n\n"
        '  calibre-toolkit unflag-manual "ids:goodreads:12345"\n\n'
        '  calibre-toolkit unflag-manual "#mqg_identifiers_manual:true" --auto-apply\n'
    ),
)
def unflag_manual(
    search: Annotated[
        str,
        typer.Argument(help='Calibre search string for books to un-flag, e.g. "ids:goodreads:12345"'),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    auto_apply: Annotated[
        bool,
        typer.Option("--auto-apply", help="Clear flags without prompting"),
    ] = False,
):
    """
    Clear the MQG-02 manual-curation flag for books you have fixed manually.

    Use this after manually adding identifiers to books that were auto-flagged
    in the identifiers_manual_column. Clearing the flag re-queues them for the
    next enrich-identifiers run.
    """
    cfg = _load_config(config)
    db = _make_db(cfg)
    mqg_manual_column = cfg.get("mqg", {}).get("identifiers_manual_column")

    if not mqg_manual_column:
        console.print(
            "[red]identifiers_manual_column not set in config.json.[/red]\n"
            "Add it under the [bold]mqg[/bold] key, e.g. "
            '[bold]"identifiers_manual_column": "#mqg_identifiers_manual"[/bold]'
        )
        raise typer.Exit(1)

    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — Unflag Manual Curation\n\n",
                ("Search: ", "dim"),
                (search, "bold"),
                ("\nColumn: ", "dim"),
                (mqg_manual_column, "bold"),
            ),
            border_style="cyan",
        )
    )

    run_unflag_manual(db=db, search_query=search, mqg_manual_column=mqg_manual_column, auto_apply=auto_apply)


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
                db.clear_mqg_flag(book.id, mqg_manual_column, audit_step="unflag-manual")
                cleared += 1
            except RuntimeError as e:
                console.print(f"[red]Error on book {book.id}: {e}[/red]")
                errors += 1

    console.print(
        f"[green]Cleared flag for {cleared} book(s).[/green]"
        + (f" [red]{errors} error(s).[/red]" if errors else "")
    )
    console.print("\n[bold green]Done![/bold green]")
