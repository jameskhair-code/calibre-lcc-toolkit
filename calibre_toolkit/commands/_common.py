"""Shared CLI plumbing for the command modules.

Owns the Typer app instance, the shared Rich console, and the config/db/AI
factories every command handler uses. Command modules import from here and
register themselves on `app`; `cli.py` imports the command modules for that
side-effect. Keeping the app and factories out of `cli.py` is what breaks
the cli ↔ commands circular-import risk.
"""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import Optional, Annotated

# Typer/Rich help text contains Unicode glyphs (e.g. → U+2192) that crash on
# legacy Windows consoles where stdout defaults to cp1252. Reconfigure before
# any Rich Console is constructed.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="calibre-toolkit",
    help="AI-assisted metadata cleanup for Calibre libraries.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
console = Console()


# ── Flag standardisation ───────────────────────────────────────────────────────
#
# The canonical names for AI-confidence-gated review flags are:
#
#   --auto-apply-high       Apply high-confidence proposals without prompting.
#   --force                 Re-process books normally skipped (already-complete,
#                           manually-flagged, etc.). Per-command help explains
#                           what is overridden.
#   --dry-run               Show proposed changes only; write nothing.
#
# Pre-v1.1 names that meant the same thing are retained as hidden aliases and
# emit a one-line deprecation warning on stderr when used, so existing scripts
# keep working. The lookup table below documents the renames.
_DEPRECATED_FLAGS: dict[str, str] = {
    "--auto-approve": "--auto-apply-high",
    "--force-lookup": "--force",
}


def _warn_deprecated_flags() -> None:
    """Print a one-line deprecation notice for any old-name flags in argv."""
    for old, new in _DEPRECATED_FLAGS.items():
        if old in sys.argv:
            console.print(
                f"[yellow]warning:[/yellow] [bold]{old}[/bold] is deprecated; "
                f"use [bold]{new}[/bold] instead. The old name still works in v1.x.",
            )


_TIER_DEFAULTS_HELP = (
    "\n\nReview tier defaults (per confidence level, applied at the bulk-approval prompt):\n"
    "  high   → all      (apply without further review)\n"
    "  medium → review   (decide per book)\n"
    "  low    → skip     (do not apply)\n"
    "Press Enter at the prompt to accept the default; pass --auto-apply-high "
    "to skip the prompt entirely for the high tier."
)

# ── Config loading ─────────────────────────────────────────────────────────────

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.json"


def _load_config(config_path: Path) -> dict:
    """Load and validate config.json; return the parsed dict unchanged.

    Validation (v1.9 item 6) is a typing layer only — the dict the commands
    receive is exactly what json.load produced, so every access-site
    `.get` default and cross-block fallback behaves as before. Shape errors
    fail loudly here with field-precise messages instead of a KeyError
    deep in a run.
    """
    from ..config_schema import ConfigValidationError, validate_config

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
    try:
        with open(config_path) as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        console.print(
            Panel(
                f"[red]{config_path} is not valid JSON:[/red] {e}",
                title="Invalid config",
                border_style="red",
            )
        )
        raise typer.Exit(1)
    try:
        warnings = validate_config(cfg)
    except ConfigValidationError as e:
        console.print(
            Panel(
                f"[red]{config_path} failed validation:[/red]\n\n"
                + "\n".join(f"  • {line}" for line in e.errors)
                + "\n\nFix the field(s) above — [bold]config.example.json[/bold] "
                "documents the expected shape.",
                title="Invalid config",
                border_style="red",
            )
        )
        raise typer.Exit(1)
    for key in warnings:
        console.print(
            f"[yellow]config.json: unknown key '{key}' — ignored.[/yellow]"
        )
    return cfg


def _make_db(cfg: dict):
    from ..db import CalibreDB
    return CalibreDB(
        library_path=cfg["library_path"],
        calibredb_path=cfg.get("calibredb_path", "calibredb"),
    )


def _apply_confirm_threshold(cfg: dict) -> int:
    """Read review.apply_confirm_threshold from config (default 20)."""
    return int(cfg.get("review", {}).get("apply_confirm_threshold", 20))


def _confirm_above_usd(cfg: dict) -> float:
    """Read usage.confirm_above_usd from config (default $1.00)."""
    return float(cfg.get("usage", {}).get("confirm_above_usd", 1.0))


def budget_guardrail(
    *,
    usage_step: str,
    n_books: int,
    model: str,
    threshold: float,
    dry_run: bool = False,
) -> None:
    """Cost-confirm gate before a step's AI phase (v1.10 item 4).

    Projects the batch cost (usage history when the sample allows, else a
    static conservative estimate — the basis is shown) and prompts when the
    projection exceeds `threshold`. Declining exits cleanly before any AI
    call. Projections at or below the threshold pass silently; --dry-run
    shows the projection but never prompts.
    """
    from ..usage import project_step_cost

    projection = project_step_cost(usage_step, n_books, model)
    if projection is None or projection.estimated_usd <= threshold:
        return
    line = (
        f"This batch: {n_books} books ≈ ${projection.estimated_usd:.2f} "
        f"({projection.basis})"
    )
    if dry_run:
        console.print(f"[dim]{line} — dry-run, proceeding without prompt.[/dim]")
        return
    if not typer.confirm(f"{line} — proceed?"):
        console.print("[yellow]Aborted — no AI calls made.[/yellow]")
        raise typer.Exit()


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

    Anthropic-only. provider_override is accepted for backwards-compatible
    CLI flags but ignored. command_key — if provided, look for an override
    block at ai.<command_key> (e.g. "lcc") before falling back to top-level.
    model_override takes precedence over config.
    """
    from ..ai import AIClient
    base_cfg = cfg.get("ai", {})

    override = base_cfg.get(command_key, {}) if command_key else {}
    ai_cfg = {**base_cfg, **override}

    if model_override:
        ai_cfg["model"] = model_override

    # Prefer the most specific api_key: command override → top-level → env.
    api_key = (
        override.get("api_key")
        or base_cfg.get("api_key")
        or os.environ.get("ANTHROPIC_API_KEY")
        or ""
    )

    if not api_key:
        console.print(
            "[red]No Anthropic API key found.[/red]\n"
            "Set [bold]ANTHROPIC_API_KEY[/bold] as an environment variable, "
            "or add it to config.json under ai.api_key (or a command override block)."
        )
        raise typer.Exit(1)

    # step_label is stamped onto every persisted usage record so the
    # cumulative-cost view in the TUI (item 13) can attribute spend by
    # step without inference.
    return AIClient(
        api_key=api_key,
        model=ai_cfg.get("model"),
        request_timeout_seconds=float(ai_cfg.get("request_timeout_seconds", 120.0)),
        max_retries=int(ai_cfg.get("max_retries", 3)),
        step_label=command_key or "",
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose", "-v",
            help="Log DEBUG-level events to stderr (default: silent)",
        ),
    ] = False,
    log_file: Annotated[
        Optional[Path],
        typer.Option(
            "--log-file",
            help="Mirror all DEBUG events to this file in addition to stderr",
        ),
    ] = None,
):
    from ..logging_config import setup_logging
    setup_logging(verbose=verbose, log_file=log_file)
    # Fires once per invocation, before any command. Old flag names remain
    # functional (kept as hidden Typer aliases) but produce a visible warning.
    _warn_deprecated_flags()
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
