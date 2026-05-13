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


def _make_ai(cfg: dict):
    from .ai import AIClient
    ai_cfg = cfg.get("ai", {})
    provider = ai_cfg.get("provider", "openai")

    # Allow API key from env var as override (more secure than config file)
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY") or ai_cfg.get("api_key", "")
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY") or ai_cfg.get("api_key", "")

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


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


if __name__ == "__main__":
    app()
