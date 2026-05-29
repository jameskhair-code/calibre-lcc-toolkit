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
from rich.text import Text

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


def _apply_confirm_threshold(cfg: dict) -> int:
    """Read review.apply_confirm_threshold from config (default 20)."""
    return int(cfg.get("review", {}).get("apply_confirm_threshold", 20))


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
    from .ai import AIClient
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


# ── Commands ───────────────────────────────────────────────────────────────────

@app.command(
    epilog=(
        "Examples:\n\n"
        '  calibre-toolkit clean-titles "tag:booker"\n\n'
        '  calibre-toolkit clean-titles "series:Man Booker Prize" --limit 10 --dry-run\n\n'
        '  calibre-toolkit clean-titles "not custom_column_cleaned:true"\n'
    ),
)
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
        typer.Option("--batch-size", "-b", help="Books per AI request (default 10)"),
    ] = 10,
    auto_apply_high: Annotated[
        bool,
        typer.Option("--auto-apply-high", help="Apply high-confidence changes without prompting"),
    ] = False,
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-n", help="Cap the number of books processed (e.g. 50)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview proposed changes without writing to Calibre"),
    ] = False,
):
    """AI-assisted author and title cleanup."""
    from .modules.authors import run_cleanup

    cfg = _load_config(config)
    db = _make_db(cfg)
    ai = _make_ai(cfg, command_key="title_author")

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
        limit=limit,
        dry_run=dry_run,
        apply_confirm_threshold=_apply_confirm_threshold(cfg),
    )


@app.command(
    epilog=(
        "Examples:\n\n"
        '  calibre-toolkit enrich-identifiers "#metadata_queue:true"\n\n'
        '  calibre-toolkit enrich-identifiers "#mqg_title_author:true" --batch-size 10\n'
    ),
)
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
        typer.Option(
            "--force", "--force-lookup",
            help="Look up all books even if they already have a sufficient identifier "
                 "(--force-lookup is a deprecated alias)",
        ),
    ] = False,
):
    """
    MQG-02: Find and add external identifiers (ISBN, Goodreads, Amazon, etc.).

    Uses Calibre's own fetch-ebook-metadata tool to query configured metadata
    sources including Goodreads. Each book requires a live web lookup.
    Books that cannot be found are automatically flagged in the manual curation
    column (mqg.identifiers_manual_column in config.json).
    """
    from .modules.identifiers import run_enrichment
    from .fetcher import IdentifierFetcher

    cfg = _load_config(config)
    db = _make_db(cfg)

    id_cfg = cfg.get("identifiers", {})
    fetch_path = _infer_fetch_path(cfg)
    fetcher_cfg = cfg.get("fetcher", {})
    timeout = fetcher_cfg.get(
        "request_timeout_seconds",
        id_cfg.get("lookup_timeout_seconds", 45),
    )
    max_retries = int(fetcher_cfg.get("max_retries", 2))
    sufficient_types = id_cfg.get("sufficient_types", ["isbn"])
    mqg_complete_requires = id_cfg.get("mqg_complete_requires", [])
    max_workers = int(id_cfg.get("max_workers", 4))
    mqg_column = cfg.get("mqg", {}).get("identifiers_column")
    mqg_manual_column = cfg.get("mqg", {}).get("identifiers_manual_column")

    fetcher = IdentifierFetcher(
        fetch_path=fetch_path,
        timeout=timeout,
        max_retries=max_retries,
    )

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
        max_workers=max_workers,
        apply_confirm_threshold=_apply_confirm_threshold(cfg),
    )


@app.command(
    epilog=(
        "Examples:\n\n"
        '  calibre-toolkit lcc-enrich "#mqg_identifiers:true and not #mqg_lcc:true"\n\n'
        '  calibre-toolkit lcc-enrich "tag:booker" --batch-size 5 --auto-apply-high\n'
    ),
)
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
        typer.Option("--dry-run", help="Preview proposed changes without writing to Calibre"),
    ] = False,
    ai_provider: Annotated[
        Optional[str],
        typer.Option("--ai-provider", help="Override AI provider for this run (e.g. openai, anthropic)"),
    ] = None,
    ai_model: Annotated[
        Optional[str],
        typer.Option("--ai-model", help="Override AI model. Accepts an alias (fast / latest / legacy) or a literal model ID."),
    ] = None,
):
    """
    MQG-03: AI-assisted Library of Congress Classification (LCC) enrichment.

    For each book, proposes:
      • lcc (call number)
      • lcc_primary_class (drop-down)
      • lcc_secondary_class (drop-down)
      • lcc_summary (one-sentence subject summary)

    Primary and secondary class are code-derived from the AI-proposed call
    number and validated against config/lcc-{primary,secondary}-canonical.csv.
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
        "lcc_summary": lcc_cfg.get("lcc_summary_column", "#lcc_summary"),
    }
    mqg_column = cfg.get("mqg", {}).get("lcc_column")
    mqg_manual_column = cfg.get("mqg", {}).get("lcc_manual_column")

    _base = cfg.get("ai", {})
    _effective_model = ai_model or {**_base, **_base.get("lcc", {})}.get("model", "(default)")

    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — MQG-03 LCC Enrichment\n\n",
                ("Search:  ", "dim"),
                (search, "bold"),
                ("\nModel:   ", "dim"),
                (_effective_model, "bold"),
            ),
            border_style="cyan",
        )
    )

    catalog_cfg = cfg.get("catalog", {})
    # `description` block is optional; it falls back to `catalog`'s discipline
    # so existing config.json files keep working without edits.
    description_cfg = cfg.get("description", {})
    description_timeout = float(
        description_cfg.get(
            "request_timeout_seconds",
            catalog_cfg.get("request_timeout_seconds", 10.0),
        )
    )
    description_max_retries = int(
        description_cfg.get(
            "max_retries",
            catalog_cfg.get("max_retries", 3),
        )
    )
    # Google Books requires an API key; env var wins over config (so a user
    # can rotate the key without touching config.json). Empty string is
    # treated as "no key" — the service short-circuits to Open Library.
    google_books_api_key = (
        os.environ.get("GOOGLE_BOOKS_API_KEY")
        or description_cfg.get("google_books_api_key", "")
    ) or None
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
        catalog_timeout=float(catalog_cfg.get("request_timeout_seconds", 10.0)),
        catalog_max_retries=int(catalog_cfg.get("max_retries", 3)),
        description_timeout=description_timeout,
        description_max_retries=description_max_retries,
        google_books_api_key=google_books_api_key,
        apply_confirm_threshold=_apply_confirm_threshold(cfg),
    )


@app.command(
    epilog=(
        "Examples:\n\n"
        '  calibre-toolkit tags-enrich "#mqg_lcc:true" --limit 10 --dry-run\n\n'
        '  calibre-toolkit tags-enrich "#mqg_lcc:true and not #mqg_tags:true"\n'
    ),
)
def tags_enrich(
    search: Annotated[
        str,
        typer.Argument(help='Calibre search string, e.g. "#mqg_lcc:true and not #mqg_tags:true"'),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", "-b", help="Books per AI request (default 20)"),
    ] = 20,
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-n", help="Cap total books processed in this run"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview proposed changes without writing to Calibre"),
    ] = False,
    ai_provider: Annotated[
        Optional[str],
        typer.Option("--ai-provider", help="Override AI provider for this run"),
    ] = None,
    ai_model: Annotated[
        Optional[str],
        typer.Option("--ai-model", help="Override AI model. Accepts an alias (fast / latest / legacy) or a literal model ID."),
    ] = None,
):
    """
    MQG-05: AI-assisted subject tag enrichment.

    Generates 4–8 flat tags per book across four categories:
      • Form     — Novel, Biography, History, Nonfiction, etc. (controlled list)
      • Subject  — Military History, Cold War, Public Health, etc.
      • Period   — World War II, Cold War, Victorian Era, etc.
      • Geography — United States, Russia, Sub-Saharan Africa, etc.

    Proposed tags replace existing tags. Confidence tiers and review
    flow match the other MQG commands. LCC data (if present) is used
    as context for more accurate subject tagging.
    """
    from .modules.tags import run_tags_enrichment

    cfg = _load_config(config)
    db = _make_db(cfg)
    ai = _make_ai(cfg, command_key="tags", provider_override=ai_provider, model_override=ai_model)

    tags_cfg  = cfg.get("tags",  {})
    lcc_cfg   = cfg.get("lcc",   {})
    mqg_column        = tags_cfg.get("mqg_column")
    mqg_manual_column = tags_cfg.get("mqg_manual_column")

    _base = cfg.get("ai", {})
    _effective_model = ai_model or {**_base, **_base.get("tags", {})}.get("model", "(default)")

    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — MQG-05 Tags Enrichment\n\n",
                ("Search:  ", "dim"),
                (search, "bold"),
                ("\nModel:   ", "dim"),
                (_effective_model, "bold"),
            ),
            border_style="cyan",
        )
    )

    run_tags_enrichment(
        db=db,
        ai=ai,
        search_query=search,
        batch_size=batch_size,
        limit=limit,
        dry_run=dry_run,
        mqg_column=mqg_column,
        mqg_manual_column=mqg_manual_column,
        lcc_summary_column=lcc_cfg.get("lcc_summary_column", "#lcc_summary"),
        lcc_secondary_column=lcc_cfg.get("secondary_class_column", "#lcc_secondary_class"),
        lcc_primary_column=lcc_cfg.get("primary_class_column", "#lcc_primary_class"),
        apply_confirm_threshold=_apply_confirm_threshold(cfg),
    )


@app.command(
    epilog=(
        "Examples:\n\n"
        "  calibre-toolkit tags-cleanup --dry-run\n\n"
        "  calibre-toolkit tags-cleanup --skip-ai           # rule-based only\n\n"
        '  calibre-toolkit tags-cleanup --search "#metadata_queue:true"\n\n'
        "  calibre-toolkit tags-cleanup --min-books 2\n"
    ),
)
def tags_cleanup(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview proposed changes without writing to Calibre"),
    ] = False,
    min_books: Annotated[
        int,
        typer.Option("--min-books", help="For the AI pass only: analyse tags used by ≥N books (default 1)"),
    ] = 1,
    skip_ai: Annotated[
        bool,
        typer.Option("--skip-ai", help="Run scanner only; do not call AI for semantic pass"),
    ] = False,
    search: Annotated[
        Optional[str],
        typer.Option("--search",
                     help='Restrict applied operations to those touching books matching this '
                          'Calibre search string. The scanner and AI pass still see the full '
                          'library vocabulary; only the apply step is scoped. '
                          'Example: --search "#metadata_queue:true".'),
    ] = None,
    ai_provider: Annotated[
        Optional[str],
        typer.Option("--ai-provider", help="Override AI provider for this run"),
    ] = None,
    ai_model: Annotated[
        Optional[str],
        typer.Option("--ai-model", help="Override AI model. Accepts an alias (fast / latest / legacy) or a literal model ID."),
    ] = None,
):
    """
    MQG-05 maintenance: normalise tag vocabulary across the whole library.

    Two-layer pipeline:

      1. Deterministic scanner — runs first on every tag. Handles obvious
         patterns rule-by-rule: LCSH date+name drops, bare date ranges,
         Calibre taxonomy noise, date-range→period lookups, formatting.
         No AI call. Free and fast. Ruleset lives in tag_scanner.py.

      2. AI semantic pass — runs on tags the scanner did not resolve.
         Handles fuzzy variant matches and near-synonyms the rules cannot
         catch. Skip this layer with --skip-ai for a pure scanner run.

    Operations are grouped by pattern_group with bulk approval per group
    (apply all / review individually / skip). Safe groups (formatting,
    taxonomy, date lookups) default to "all"; everything else defaults
    to "review".

    Use --search to restrict the apply step to a specific subset of the
    library — handy for cleaning up vocabulary inside a batch (e.g. the
    metadata queue) without touching the rest of the library. Frequency
    counts and AI synonym judgements still use the full vocabulary so the
    cleanup remains as accurate as a library-wide run.
    """
    from .modules.tags import run_tags_cleanup

    cfg = _load_config(config)
    db = _make_db(cfg)
    ai = (
        _make_ai(cfg, command_key="tags", provider_override=ai_provider, model_override=ai_model)
        if not skip_ai else None
    )

    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — MQG-05 Tags Cleanup\n\n",
                ("Mode: ", "dim"),
                ("Dry run — no writes" if dry_run else "Interactive review", "bold"),
                ("\nLayers: ", "dim"),
                ("Scanner only" if skip_ai else "Scanner + AI", "bold"),
                ("\nScope:  ", "dim"),
                (search if search else "Whole library", "bold"),
            ),
            border_style="cyan",
        )
    )

    run_tags_cleanup(
        db=db, ai=ai,
        min_books=min_books,
        dry_run=dry_run,
        skip_ai=skip_ai,
        search_query=search,
    )


@app.command(
    epilog=(
        "Examples:\n\n"
        '  calibre-toolkit comments-enrich "#mqg_lcc:true" --limit 5 --dry-run\n\n'
        '  calibre-toolkit comments-enrich "#mqg_lcc:true and not #mqg_comments:true"\n'
    ),
)
def comments_enrich(
    search: Annotated[
        str,
        typer.Argument(help='Calibre search string, e.g. "#mqg_lcc:true and not #mqg_comments:true"'),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", "-b", help="Books per AI request (default 5)"),
    ] = 5,
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-n", help="Cap total books processed in this run (for testing)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview proposed changes without writing to Calibre"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Include books previously flagged for manual review"),
    ] = False,
    ai_model: Annotated[
        Optional[str],
        typer.Option("--ai-model", help="Override AI model. Accepts an alias (fast / latest / legacy) or a literal model ID."),
    ] = None,
):
    """
    MQG-04: AI-assisted book comments / description enrichment.

    For each book the AI generates a structured comment following the rules in
    rules/comments.md (fiction vs. non-fiction handled differently) and a
    0–10 must-read score with a short rationale. Voice and angle follow
    rules/reader_profile.md.
    """
    from .modules.comments import run_comments_enrichment

    cfg = _load_config(config)
    db = _make_db(cfg)
    ai = _make_ai(cfg, command_key="comments", model_override=ai_model)

    comments_cfg = cfg.get("comments", {})
    mqg_column         = comments_cfg.get("mqg_column")
    mqg_manual_column  = comments_cfg.get("mqg_manual_column")
    lcc_summary_column = comments_cfg.get("lcc_summary_column", "#lcc_summary")

    _base = cfg.get("ai", {})
    _effective_model = ai_model or {**_base, **_base.get("comments", {})}.get("model", "(default)")

    mode_label = "Dry Run" if dry_run else "Enrich"
    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                f" — MQG-04 Comments ({mode_label})\n\n",
                ("Search:  ", "dim"),
                (search, "bold"),
                ("\nModel:   ", "dim"),
                (_effective_model, "bold"),
            ),
            border_style="cyan",
        )
    )

    run_comments_enrichment(
        db=db,
        ai=ai,
        search_query=search,
        batch_size=batch_size,
        limit=limit,
        dry_run=dry_run,
        force=force,
        mqg_column=mqg_column,
        mqg_manual_column=mqg_manual_column,
        lcc_summary_column=lcc_summary_column,
        apply_confirm_threshold=_apply_confirm_threshold(cfg),
    )


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


@app.command(
    epilog=(
        "Examples:\n\n"
        "  calibre-toolkit tags-review\n\n"
        '  calibre-toolkit tags-review "tag:Booker" --limit 20\n\n'
        "  calibre-toolkit tags-review --no-ai --limit 50\n\n"
        "  calibre-toolkit tags-review --auto-apply-high --limit 100\n"
    ),
)
def tags_review(
    search: Annotated[
        Optional[str],
        typer.Argument(
            help="Calibre search string (default: books where #tags_reviewed is not set)"
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-n", help="Max books per session"),
    ] = None,
    no_ai: Annotated[
        bool,
        typer.Option("--no-ai", help="Skip AI assessment; manual review only"),
    ] = False,
    auto_approve: Annotated[
        bool,
        typer.Option(
            "--auto-apply-high", "--auto-approve",
            help="Auto-lock books where AI says complete + high confidence "
                 "(--auto-approve is a deprecated alias)",
        ),
    ] = False,
    ai_provider: Annotated[
        Optional[str],
        typer.Option("--ai-provider", help="Override AI provider for this run"),
    ] = None,
    ai_model: Annotated[
        Optional[str],
        typer.Option("--ai-model", help="Override AI model. Accepts an alias (fast / latest / legacy) or a literal model ID."),
    ] = None,
):
    """
    MQG-05: Interactive per-book tag review with AI assessment and locking.

    For each unreviewed book, shows the full metadata context (title, authors,
    description, current tags, LCC classification) and runs an AI assessment
    of tag completeness. You choose to:

      [a] approve AI suggestions (apply proposed tags + lock)
      [k] keep current tags as-is (lock without changes)
      [e] edit tags inline (pre-filled from AI suggestion, then lock)
      [s] skip this book (leave unreviewed)
      [q] quit the session

    Books are ordered by tag count ascending (fewest tags first).
    The #tags_reviewed column is set to Yes for every locked book.
    """
    from .modules.tags_review import run_tags_review

    cfg = _load_config(config)
    db  = _make_db(cfg)
    ai  = (
        _make_ai(cfg, command_key="tags", provider_override=ai_provider, model_override=ai_model)
        if not no_ai else None
    )

    tags_cfg = cfg.get("tags", {})
    lcc_cfg  = cfg.get("lcc",  {})
    reviewed_column = tags_cfg.get("reviewed_column", "#tags_reviewed")

    effective_search = search or f"not {reviewed_column}:true"

    _base = cfg.get("ai", {})
    _effective_model = ai_model or {**_base, **_base.get("tags", {})}.get("model", "(default)")

    mode_label = "Manual only" if no_ai else _effective_model
    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — MQG-05 Tags Review\n\n",
                ("Search:   ", "dim"),
                (effective_search, "bold"),
                ("\nProvider: ", "dim"),
                (mode_label, "bold"),
                ("\nColumn:   ", "dim"),
                (reviewed_column, "bold"),
            ),
            border_style="cyan",
        )
    )

    run_tags_review(
        db=db,
        ai=ai,
        search_query=effective_search,
        reviewed_column=reviewed_column,
        mqg_column=tags_cfg.get("mqg_column"),
        lcc_summary_column=lcc_cfg.get("lcc_summary_column", "#lcc_summary"),
        lcc_primary_column=lcc_cfg.get("primary_class_column", "#lcc_primary_class"),
        lcc_secondary_column=lcc_cfg.get("secondary_class_column", "#lcc_secondary_class"),
        limit=limit,
        no_ai=no_ai,
        auto_approve_complete=auto_approve,
    )


@app.command(
    name="audit-confidence",
    epilog=(
        "Examples:\n\n"
        "  calibre-toolkit audit-confidence\n\n"
        "  calibre-toolkit audit-confidence --step comments-enrich --sample-size 30\n\n"
        "  calibre-toolkit audit-confidence --step tags-enrich,lcc-enrich --threshold 0.8\n"
    ),
)
def audit_confidence(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    sample_size: Annotated[
        int,
        typer.Option("--sample-size", "-n",
                     help="Max records to sample per (step, tier) group"),
    ] = 5,
    step: Annotated[
        Optional[str],
        typer.Option("--step",
                     help='Comma-separated step filter (e.g. "comments-enrich,tags-enrich"). '
                          'Default: all steps in the audit log.'),
    ] = None,
    threshold: Annotated[
        float,
        typer.Option("--threshold",
                     help="Strict-precision floor; tiers below this are flagged"),
    ] = 0.7,
    audit_log: Annotated[
        Optional[Path],
        typer.Option("--audit-log",
                     help="Override audit log path (default: $CALIBRE_TOOLKIT_AUDIT_LOG "
                          "or ~/.calibre-toolkit/audit.log)"),
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o",
                     help="Where to append the calibration session record "
                          "(default: ~/.calibre-toolkit/calibration.jsonl)"),
    ] = None,
    seed: Annotated[
        Optional[int],
        typer.Option("--seed", help="Random seed for reproducible sampling"),
    ] = None,
):
    """
    Measure how well confidence tiers predict accuracy.

    Samples applied AI writes from ~/.calibre-toolkit/audit.log, prompts
    you to rate each as correct / minor / wrong, and computes per-tier
    strict and lenient precision. Tiers whose strict precision falls
    below --threshold are flagged for rule review.

    The command is purely observational — it does not change any field
    in Calibre. Results are appended to ~/.calibre-toolkit/calibration.jsonl
    as one JSONL line per session.
    """
    from .commands.audit import run_audit_confidence

    cfg = _load_config(config)
    db = _make_db(cfg)

    if audit_log is not None:
        audit_log_path = audit_log
    else:
        env = os.environ.get("CALIBRE_TOOLKIT_AUDIT_LOG")
        audit_log_path = Path(env).expanduser() if env else (
            Path.home() / ".calibre-toolkit" / "audit.log"
        )
    output_path = output or (Path.home() / ".calibre-toolkit" / "calibration.jsonl")

    steps_filter: Optional[list[str]] = None
    if step:
        steps_filter = [s.strip() for s in step.split(",") if s.strip()]

    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — audit-confidence\n\n",
                ("Audit log: ", "dim"),
                (str(audit_log_path), "bold"),
                ("\nOutput:    ", "dim"),
                (str(output_path), "bold"),
                ("\nSample:    ", "dim"),
                (f"{sample_size} per (step, tier)", "bold"),
                ("\nThreshold: ", "dim"),
                (f"{threshold:.0%} strict precision", "bold"),
            ),
            border_style="cyan",
        )
    )

    run_audit_confidence(
        db=db,
        audit_log_path=audit_log_path,
        output_path=output_path,
        sample_size=sample_size,
        threshold=threshold,
        steps_filter=steps_filter,
        seed=seed,
    )


@app.command(
    name="audit-trajectory",
    epilog=(
        "Examples:\n\n"
        "  calibre-toolkit audit-trajectory\n\n"
        "  calibre-toolkit audit-trajectory --calibration ./calibration.jsonl\n"
    ),
)
def audit_trajectory(
    calibration: Annotated[
        Optional[Path],
        typer.Option("--calibration",
                     help="Path to the calibration session log "
                          "(default: ~/.calibre-toolkit/calibration.jsonl)"),
    ] = None,
):
    """
    Show how each confidence tier's strict precision has trended across
    calibration sessions.

    Reads the history written by audit-confidence and renders a
    per-(step, tier) sparkline with first/latest strict precision and the
    change between them. Purely observational — reads one file, writes nothing.
    """
    from .commands.audit import run_trajectory

    calibration_path = calibration or (
        Path.home() / ".calibre-toolkit" / "calibration.jsonl"
    )
    run_trajectory(calibration_path)


@app.command(
    name="audit-log",
    epilog=(
        "Examples:\n\n"
        "  calibre-toolkit audit-log\n\n"
        "  calibre-toolkit audit-log --book-id 5417\n\n"
        "  calibre-toolkit audit-log --step lcc-enrich --since 2026-05-28\n\n"
        "  calibre-toolkit audit-log --field comments --limit 100\n"
    ),
)
def audit_log_show(
    field: Annotated[
        Optional[str],
        typer.Option("--field",
                     help='Filter by metadata field (e.g. "comments", "#lcc").'),
    ] = None,
    book_id: Annotated[
        Optional[int],
        typer.Option("--book-id", help="Filter by Calibre book id."),
    ] = None,
    step: Annotated[
        Optional[str],
        typer.Option("--step",
                     help='Filter by pipeline step (e.g. "lcc-enrich"). '
                          "The audit log carries no session marker, so step is "
                          "the grouping to query by."),
    ] = None,
    since: Annotated[
        Optional[str],
        typer.Option("--since",
                     help="Only entries on/after this ISO date or timestamp "
                          "(e.g. 2026-05-28)."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit",
                     help="Max rows to show, most recent first-in-window "
                          "(0 = all)."),
    ] = 50,
    audit_log: Annotated[
        Optional[Path],
        typer.Option("--audit-log",
                     help="Override audit log path (default: $CALIBRE_TOOLKIT_AUDIT_LOG "
                          "or ~/.calibre-toolkit/audit.log)"),
    ] = None,
):
    """
    Query the persistent audit trail without grep.

    Reads ~/.calibre-toolkit/audit.log (one JSONL line per metadata write
    since v1.1) and renders matching entries as a compact table. Filter by
    --field, --book-id, --step, and/or --since. Purely read-only — opens one
    file and writes nothing.
    """
    from .commands.audit_log import parse_since, run_audit_log_show

    if audit_log is not None:
        audit_log_path = audit_log
    else:
        env = os.environ.get("CALIBRE_TOOLKIT_AUDIT_LOG")
        audit_log_path = Path(env).expanduser() if env else (
            Path.home() / ".calibre-toolkit" / "audit.log"
        )

    since_dt = parse_since(since) if since else None
    run_audit_log_show(
        audit_log_path,
        field=field, book_id=book_id, step=step, since=since_dt, limit=limit,
    )


@app.command(
    epilog=(
        "Examples:\n\n"
        "  calibre-toolkit regrade --step lcc-enrich --before 2026-05-15 --dry-run\n\n"
        "  calibre-toolkit regrade --step lcc-enrich --before 2026-05-15\n\n"
        "  calibre-toolkit regrade --step tags-enrich --before 2026-05-01 --force\n"
    ),
)
def regrade(
    step: Annotated[
        str,
        typer.Option("--step",
                     help="Enrichment step to re-grade: lcc-enrich, "
                          "comments-enrich, or tags-enrich."),
    ],
    before: Annotated[
        str,
        typer.Option("--before",
                     help="Re-grade books whose latest write for this step "
                          "predates this ISO date/timestamp (the date the rule "
                          "changed). e.g. 2026-05-15"),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="List the stale books without re-running."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Include manually-curated books (skipped by default)."),
    ] = False,
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-n", help="Cap how many stale books to re-grade."),
    ] = None,
    audit_log: Annotated[
        Optional[Path],
        typer.Option("--audit-log",
                     help="Override audit log path (default: $CALIBRE_TOOLKIT_AUDIT_LOG "
                          "or ~/.calibre-toolkit/audit.log)"),
    ] = None,
    ai_model: Annotated[
        Optional[str],
        typer.Option("--ai-model", help="Override AI model (alias fast/latest/legacy or a literal id)."),
    ] = None,
):
    """
    Re-run an enrichment step on books made stale by a rule change.

    Finds books whose latest audit entry for --step predates --before (the date
    you changed the rule) and re-runs just those against the current prompt,
    reusing the step's normal review/apply flow. Re-grade writes are marked so
    they don't pollute calibration, and manually-curated books are skipped
    unless --force. Scope: lcc-enrich, comments-enrich, tags-enrich.
    """
    from .commands.regrade import run_regrade, STEPS
    from .commands.audit_log import parse_since

    if step not in STEPS:
        raise typer.BadParameter(
            f"'{step}' is not a re-gradable step. Choose one of: {', '.join(STEPS)}"
        )
    before_dt = parse_since(before)

    cfg = _load_config(config)
    db = _make_db(cfg)

    if audit_log is not None:
        audit_log_path = audit_log
    else:
        env = os.environ.get("CALIBRE_TOOLKIT_AUDIT_LOG")
        audit_log_path = Path(env).expanduser() if env else (
            Path.home() / ".calibre-toolkit" / "audit.log"
        )

    # AI client is only needed for an actual run; a dry-run shouldn't require
    # an API key. command_key is the step prefix (lcc/comments/tags).
    ai = None
    if not dry_run:
        ai = _make_ai(cfg, command_key=step.removesuffix("-enrich"), model_override=ai_model)

    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — Re-grade\n\n",
                ("Step:    ", "dim"), (step, "bold"),
                ("\nBefore:  ", "dim"), (before, "bold"),
            ),
            border_style="cyan",
        )
    )

    run_regrade(
        db, ai, cfg,
        step=step, before=before_dt, before_label=before,
        audit_path=audit_log_path, dry_run=dry_run, force=force, limit=limit,
        apply_confirm_threshold=_apply_confirm_threshold(cfg),
    )


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
    from .tui.app import main as tui_main
    tui_main(config_path=config)


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
    Validate config, library, calibredb, API key, and custom columns.

    Read-only. Exits non-zero on any failure so it can be used in CI or as a
    pre-flight check before running a batch.
    """
    from .setup import run_doctor
    raise typer.Exit(run_doctor(config, console))


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
    from .setup import run_init
    raise typer.Exit(run_init(config, console))


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
    from .setup import run_setup_columns
    raise typer.Exit(run_setup_columns(config, console))


# Append the tier-defaults block to every command that runs a tiered
# bulk-approval prompt. Typer reads __doc__ when rendering --help, so
# mutating it after definition keeps the single-source-of-truth block out
# of every individual docstring.
for _cmd in (clean_titles, enrich_identifiers, lcc_enrich,
             tags_enrich, comments_enrich):
    _cmd.__doc__ = (_cmd.__doc__ or "").rstrip() + "\n" + _TIER_DEFAULTS_HELP + "\n"


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
    from .logging_config import setup_logging
    setup_logging(verbose=verbose, log_file=log_file)
    # Fires once per invocation, before any command. Old flag names remain
    # functional (kept as hidden Typer aliases) but produce a visible warning.
    _warn_deprecated_flags()
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


if __name__ == "__main__":
    app()
