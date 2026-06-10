"""init — interactive first-run setup wizard."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ._common import app, console, DEFAULT_CONFIG_PATH


@app.command(
    epilog=(
        "Examples:\n\n"
        "  calibre-toolkit init                          # fresh install\n\n"
        "  calibre-toolkit init --config ./alt-config.json\n"
    ),
)
def init(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Where to write config.json"),
    ] = DEFAULT_CONFIG_PATH,
):
    """
    Interactive setup wizard. Prompts for library path, calibredb, and API
    key, verifies each, then writes a complete config.json atomically.

    Use this for a fresh install. Existing configs are not overwritten
    without explicit confirmation.
    """
    from ..setup import run_init
    raise typer.Exit(run_init(config, console))
