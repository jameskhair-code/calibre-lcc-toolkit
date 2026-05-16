"""
Calibre Toolkit CLI entry point.
Run: calibre-toolkit --help
"""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import Optional, Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

app = typer.Typer(
    name="calibre-toolkit",
    help="AI-assisted metadata cleanup for Calibre libraries.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
console = Console()

# ── Config loading ─────────────────────────────────────────────────────────────

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def _load_config(config_path: Path) -> dict:
    if not config_path.exists():
        console.print(
            Panel(
                f"[red]Config file not found:[/red] {config_path}\n\n"
                "Copy [bold]config.example.json[/bold] to [bold]config.json[/bold] "
                "and fill in your library path and API key.",
                title="Setup required",
                border_style="red",
            )
        )
        raise typer.Exit(1)
    with open(config_path) as f:
        return json.load(f)


def _make_db(cfg: dict):
    from .db import CalibreDB
    return CalibreDB(
        library_path=cfg["library_path"],
        calibredb_path=cfg.get("calibredb_path", "calibredb"),
    )


def _infer_fetch_path(cfg: dict) -> str:
    """Infer fetch-ebook-metadata path from config or from calibredb_path sibling."""
    explicit = cfg.get("identifiers", {}).get("fetch_ebook_metadata_path")
    if explicit:
        return explicit
    calibredb = cfg.get("calibredb_path", "calibredb")
    p = Path(calibredb)
    if p.parent != Path("."):
        suffix = ".exe" if calibredb.lower().endswith(".exe") else ""
        return str(p.parent / f"fetch-ebook-metadata{suffix}")
    return "fetch-ebook-metadata"


def _make_ai(
    cfg: dict,
    command_key: str | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
):
    """Build an AIClient from config.

    command_key — if provided, look for an override block at ai.<command_key>
    (e.g. "lcc") before falling back to the top-level ai block.
    provider_override / model_override — CLI flags that take precedence over config.
    """
    from .ai import AIClient
    base_cfg = cfg.get("ai", {})

    # Merge: command-specific block overrides the top-level block
    override = base_cfg.get(command_key, {}) if command_key else {}
    ai_cfg = {**base_cfg, **override}

    if provider_override:
        ai_cfg["provider"] = provider_override
    if model_override:
        ai_cfg["model"] = model_override

    provider = ai_cfg.get("provider", "openai")

    # Allow API key from env var as override (more secure than config file)
    # Config supports provider-specific keys: ai.openai_api_key / ai.anthropic_api_key
    # falling back to ai.api_key for whichever provider is currently default.
    if provider == "openai":
        api_key = (os.environ.get("OPENAI_API_KEY")
                   or ai_cfg.get("openai_api_key")
                   or (ai_cfg.get("api_key", "") if ai_cfg.get("provider", "openai") == "openai" else ""))
    else:
        api_key = (os.environ.get("ANTHROPIC_API_KEY")
                   or ai_cfg.get("anthropic_api_key")
                   or (ai_cfg.get("api_key", "") if ai_cfg.get("provider", "openai") != "openai" else ""))

    if not api_key:
        console.print(
            f"[red]No API key found for provider '{provider}'.[/red]\n"
            f"Set [bold]OPENAI_API_KEY[/bold] (or ANTHROPIC_API_KEY) as an environment variable, "
            f"or add it to config.json under ai.api_key."
        )
        raise typer.Exit(1)

    return AIClient(
        provider=provider,
        api_key=api_key,
        model=ai_cfg.get("model"),
    )


# ── Commands ───────────────────────────────────────────────────────────────────

@app.command()
def clean_titles(
    search: Annotated[
        str,
        typer.Argument(help='Calibre search string, e.g. "tag:booker" or "series:Booker"'),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", "-b", help="Books per AI request (default 50)"),
    ] = 50,
    auto_apply_high: Annotated[
        bool,
        typer.Option("--auto-apply-high", help="Apply high-confidence changes without prompting"),
    ] = False,
):
    """
    AI-assisted author and title cleanup.

    Examples:

        calibre-toolkit clean-titles "tag:booker"

        calibre-toolkit clean-titles "series:Man Booker Prize"

        calibre-toolkit clean-titles "not custom_column_cleaned:true"
    """
    from .modules.authors import run_cleanup

    cfg = _load_config(config)
    db = _make_db(cfg)
    ai = _make_ai(cfg)

    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — Author & Title Cleanup\n\n",
                ("Search: ", "dim"),
                (search, "bold"),
            ),
            border_style="cyan",
        )
    )

    mqg_column = cfg.get("mqg", {}).get("title_author_column")

    run_cleanup(
        db=db,
        ai=ai,
        search_query=search,
        batch_size=batch_size,
        auto_apply_high=auto_apply_high,
        mqg_column=mqg_column,
    )


@app.command()
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
        typer.Option("--force-lookup", help="Look up all books even if already sufficient"),
    ] = False,
):
    """
    MQG-02: Find and add external identifiers (ISBN, Goodreads, Amazon, etc.).

    Uses Calibre's own fetch-ebook-metadata tool to query configured metadata
    sources including Goodreads. Each book requires a live web lookup.
    Books that cannot be found are automatically flagged in the manual curation
    column (mqg.identifiers_manual_column in config.json).

    Examples:

        calibre-toolkit enrich-identifiers "#metadata_queue:true"

        calibre-toolkit enrich-identifiers "#mqg_title_author:true" --batch-size 10
    """
    from .modules.identifiers import run_enrichment
    from .fetcher import IdentifierFetcher

    cfg = _load_config(config)
    db = _make_db(cfg)

    id_cfg = cfg.get("identifiers", {})
    fetch_path = _infer_fetch_path(cfg)
    timeout = id_cfg.get("lookup_timeout_seconds", 45)
    sufficient_types = id_cfg.get("sufficient_types", ["isbn"])
    mqg_complete_requires = id_cfg.get("mqg_complete_requires", [])
    mqg_column = cfg.get("mqg", {}).get("identifiers_column")
    mqg_manual_column = cfg.get("mqg", {}).get("identifiers_manual_column")

    fetcher = IdentifierFetcher(fetch_path=fetch_path, timeout=timeout)

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
    )


@app.command()
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
        typer.Option("--dry-run", help="Show what the AI would write vs. current values — no changes saved"),
    ] = False,
    ai_provider: Annotated[
        Optional[str],
        typer.Option("--ai-provider", help="Override AI provider for this run (e.g. openai, anthropic)"),
    ] = None,
    ai_model: Annotated[
        Optional[str],
        typer.Option("--ai-model", help="Override AI model for this run (e.g. gpt-4o, claude-sonnet-4-6)"),
    ] = None,
):
    """
    MQG-03: AI-assisted Library of Congress Classification (LCC) enrichment.

    For each book, proposes:
      • lcc (call number)
      • lcc_primary_class (drop-down)
      • lcc_secondary_class (drop-down)
      • lcc_class_path (one-sentence subject summary)

    Primary and secondary class are code-derived from the AI-proposed call
    number and validated against config/lcc-{primary,secondary}-canonical.csv.

    Examples:

        calibre-toolkit lcc-enrich "#mqg_identifiers:true and not #mqg_lcc:true"

        calibre-toolkit lcc-enrich "tag:booker" --batch-size 5 --auto-apply-high
    """
    from .modules.lcc import run_lcc_enrichment

    cfg = _load_config(config)
    db = _make_db(cfg)
    ai = _make_ai(cfg, command_key="lcc", provider_override=ai_provider, model_override=ai_model)

    lcc_cfg = cfg.get("lcc", {})
    columns = {
        "lcc": lcc_cfg.get("lcc_column", "#lcc"),
        "lcc_primary_class": lcc_cfg.get("primary_class_column", "#lcc_primary_class"),
        "lcc_secondary_class": lcc_cfg.get("secondary_class_column", "#lcc_secondary_class"),
        "lcc_class_path": lcc_cfg.get("class_path_column", "#lcc_class_path"),
    }
    mqg_column = cfg.get("mqg", {}).get("lcc_column")
    mqg_manual_column = cfg.get("mqg", {}).get("lcc_manual_column")

    # Resolve effective AI config for display (CLI overrides take precedence)
    _base = cfg.get("ai", {})
    _lcc_ai = {**_base, **_base.get("lcc", {})}
    _effective_provider = ai_provider or _lcc_ai.get("provider", "openai")
    _effective_model = ai_model or _lcc_ai.get("model", "(default)")

    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — MQG-03 LCC Enrichment\n\n",
                ("Search:    ", "dim"),
                (search, "bold"),
                ("\nProvider:  ", "dim"),
                (f"{_effective_provider} / {_effective_model}", "bold"),
            ),
            border_style="cyan",
        )
    )

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
    )


@app.command()
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
    """
    Scan and fix malformed identifiers (UUIDs, urnisbn/ format, empty values).

    Examples:

        calibre-toolkit clean-identifiers "all"

        calibre-toolkit clean-identifiers "#mqg_identifiers:true"
    """
    from .modules.clean_identifiers import run_clean_identifiers

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


@app.command()
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

    Examples:

        calibre-toolkit unflag-manual "ids:goodreads:12345"

        calibre-toolkit unflag-manual "#mqg_identifiers_manual:true" --auto-apply
    """
    from .modules.identifiers import run_unflag_manual

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


@app.command()
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


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


if __name__ == "__main__":
    app()
