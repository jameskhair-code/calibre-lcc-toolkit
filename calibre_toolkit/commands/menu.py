"""menu — launch the interactive Terminal UI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ._common import app, DEFAULT_CONFIG_PATH


@app.command(
    epilog=(
        "Examples:\n\n"
        "  calibre-toolkit menu\n\n"
        "  py -m calibre_toolkit.tui\n"
    ),
)
def menu(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
):
    """
    Launch the interactive Terminal UI menu.

    Full-screen two-panel interface showing MQG pipeline progress and
    letting you run any command without remembering CLI syntax.
    """
    from ..tui.app import main as tui_main
    tui_main(config_path=config)
