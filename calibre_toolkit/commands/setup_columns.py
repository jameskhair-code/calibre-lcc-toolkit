"""setup-columns — create the required Calibre custom columns."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ._common import app, console, DEFAULT_CONFIG_PATH


@app.command(
    epilog=(
        "Examples:\n\n"
        "  calibre-toolkit setup-columns                  # create / verify the 14 columns\n\n"
        "  calibre-toolkit setup-columns --config ./alt-config.json\n"
    ),
)
def setup_columns(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
):
    """
    Create the 14 required Calibre custom columns via calibredb.

    Idempotent — columns that already exist with the correct type are
    skipped. Enumeration values for #lcc_primary_class and
    #lcc_secondary_class are loaded from config/lcc-*-canonical.csv.
    Calibre must be closed before running.
    """
    from ..setup import run_setup_columns
    raise typer.Exit(run_setup_columns(config, console))
