"""library-info — show library path, book counts, and calibredb version."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.text import Text

from ._common import app, console, DEFAULT_CONFIG_PATH, _load_config, _make_db


@app.command(
    epilog=(
        "Examples:\n\n"
        "  calibre-toolkit library-info\n\n"
        "  calibre-toolkit library-info --config ./alt-config.json\n"
    ),
)
def library_info(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
):
    """
    Show library path, book counts, and calibredb version.

    Use this to confirm the toolkit is pointing at the right library and
    to diagnose scan-scope discrepancies between SQLite and calibredb.
    """
    import subprocess as _sp

    cfg = _load_config(config)
    db = _make_db(cfg)

    sqlite_total = db.count_books()

    # Ask calibredb for its count via search "all" (may differ if a restriction is active)
    cmd = [
        cfg.get("calibredb_path", "calibredb"),
        "search",
        "--library-path", cfg["library_path"],
        "all",
    ]
    r = _sp.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0 and r.stdout.strip():
        calibredb_ids = [x for x in r.stdout.strip().split(",") if x.strip().isdigit()]
        calibredb_count = len(calibredb_ids)
    else:
        calibredb_count = 0

    # calibredb version
    ver_r = _sp.run(
        [cfg.get("calibredb_path", "calibredb"), "--version"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    calibredb_ver = ver_r.stdout.strip().splitlines()[0] if ver_r.returncode == 0 else "unknown"

    console.print(
        Panel(
            Text.assemble(("Calibre Toolkit", "bold cyan"), " — Library Info"),
            border_style="cyan",
        )
    )
    console.print(f"  [bold]Library path:[/bold]  {cfg['library_path']}")
    console.print(f"  [bold]calibredb:[/bold]      {cfg.get('calibredb_path', 'calibredb')}")
    console.print(f"  [bold]calibredb ver:[/bold]  {calibredb_ver}")
    console.print()
    console.print(f"  [bold]Books in SQLite:[/bold]          [green]{sqlite_total}[/green]")
    console.print(f"  [bold]Books via calibredb search:[/bold] [{'green' if calibredb_count == sqlite_total else 'yellow'}]{calibredb_count}[/{'green' if calibredb_count == sqlite_total else 'yellow'}]")

    if calibredb_count != sqlite_total:
        diff = sqlite_total - calibredb_count
        console.print(
            f"\n  [yellow]⚠ {diff} book(s) are visible in SQLite but not returned by calibredb search.[/yellow]\n"
            "  This usually means Calibre has an active [bold]Restriction[/bold] saved in the GUI\n"
            "  (the dropdown next to the search bar, separate from Virtual Library).\n\n"
            "  [dim]The toolkit's 'all' query now reads IDs directly from SQLite,\n"
            "  so clean-identifiers \"all\" will correctly scan all books.[/dim]"
        )
    else:
        console.print("\n  [green]✓ SQLite and calibredb counts match — no restriction detected.[/green]")
