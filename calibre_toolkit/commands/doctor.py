"""doctor — pre-flight validation of config, library, and environment."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ._common import app, console, DEFAULT_CONFIG_PATH


@app.command(
    epilog=(
        "Examples:\n\n"
        "  calibre-toolkit doctor                       # pre-flight check\n\n"
        "  calibre-toolkit doctor && calibre-toolkit lcc-enrich ...   # gate a batch\n"
    ),
)
def doctor(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
):
    """
    Validate config, library, calibredb, API key, custom columns, and the
    toolkit state files (audit log, calibration and rule-revision logs,
    OL work-key cache).

    Read-only. Exits non-zero on any failure so it can be used in CI or as a
    pre-flight check before running a batch.
    """
    from ..setup import run_doctor
    raise typer.Exit(run_doctor(config, console))
