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

    # Build a provider→key map so switching providers doesn't use the wrong key.
    # ai.api_key belongs to the top-level ai.provider.
    # ai.lcc.api_key (or other command override) belongs to that block's provider.
    # Explicit ai.openai_api_key / ai.anthropic_api_key always win.
    provider_keys: dict[str, str] = {}
    top_provider = base_cfg.get("provider", "openai")
    if base_cfg.get("api_key"):
        provider_keys[top_provider] = base_cfg["api_key"]
    if override.get("provider") and override.get("api_key"):
        provider_keys[override["provider"]] = override["api_key"]
    for p in ("openai", "anthropic"):
        if ai_cfg.get(f"{p}_api_key"):
            provider_keys[p] = ai_cfg[f"{p}_api_key"]

    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY") or provider_keys.get("openai", "")
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY") or provider_keys.get("anthropic", "")

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
      • lcc_summary (one-sentence subject summary)

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
        "lcc_summary": lcc_cfg.get("lcc_summary_column", "#lcc_summary"),
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
        typer.Option("--dry-run", help="Show proposed tags without writing"),
    ] = False,
    ai_provider: Annotated[
        Optional[str],
        typer.Option("--ai-provider", help="Override AI provider for this run"),
    ] = None,
    ai_model: Annotated[
        Optional[str],
        typer.Option("--ai-model", help="Override AI model for this run"),
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

    Examples:

        calibre-toolkit tags-enrich "#mqg_lcc:true" --limit 10 --dry-run

        calibre-toolkit tags-enrich "#mqg_lcc:true and not #mqg_tags:true"
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
    _tags_ai = {**_base, **_base.get("tags", {})}
    _effective_provider = ai_provider or _tags_ai.get("provider", "openai")
    _effective_model    = ai_model    or _tags_ai.get("model", "(default)")

    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                " — MQG-05 Tags Enrichment\n\n",
                ("Search:    ", "dim"),
                (search, "bold"),
                ("\nProvider:  ", "dim"),
                (f"{_effective_provider} / {_effective_model}", "bold"),
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
    )


@app.command()
def tags_cleanup(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = DEFAULT_CONFIG_PATH,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show proposed merges without applying"),
    ] = False,
    min_books: Annotated[
        int,
        typer.Option("--min-books", help="For the AI pass only: analyse tags used by ≥N books (default 1)"),
    ] = 1,
    skip_ai: Annotated[
        bool,
        typer.Option("--skip-ai", help="Run scanner only; do not call AI for semantic pass"),
    ] = False,
    ai_provider: Annotated[
        Optional[str],
        typer.Option("--ai-provider", help="Override AI provider for this run"),
    ] = None,
    ai_model: Annotated[
        Optional[str],
        typer.Option("--ai-model", help="Override AI model for this run"),
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

    Examples:

        calibre-toolkit tags-cleanup --dry-run

        calibre-toolkit tags-cleanup --skip-ai    # rule-based only

        calibre-toolkit tags-cleanup --min-books 2
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
            ),
            border_style="cyan",
        )
    )

    run_tags_cleanup(
        db=db, ai=ai,
        min_books=min_books,
        dry_run=dry_run,
        skip_ai=skip_ai,
    )


@app.command()
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
        typer.Option("--dry-run", help="Show what the AI would write — no changes saved"),
    ] = False,
    tone_test: Annotated[
        bool,
        typer.Option("--tone-test", help="Generate 3 voice variants for one book; no writes"),
    ] = False,
    ai_provider: Annotated[
        Optional[str],
        typer.Option("--ai-provider", help="Override AI provider for this run (e.g. openai, anthropic)"),
    ] = None,
    ai_model: Annotated[
        Optional[str],
        typer.Option("--ai-model", help="Override AI model for this run"),
    ] = None,
):
    """
    MQG-04: AI-assisted book comments / description enrichment.

    For each book, generates a structured HTML comment with six sections:
      • The Book          — what it is and its core argument
      • Why It Matters    — its significance
      • Award Context     — the award(s) and year
      • Something You Might Not Know  — (conditional) surprising fact
      • Why Read It       — the honest sell
      • Source Notes      — transparency about AI generation

    Tone follows rules/reader_profile.md. Use --tone-test to see three voice
    variants for one book before committing to a style.

    Examples:

        calibre-toolkit comments-enrich "#mqg_lcc:true" --limit 5 --dry-run

        calibre-toolkit comments-enrich "#mqg_lcc:true" --tone-test

        calibre-toolkit comments-enrich "#mqg_lcc:true and not #mqg_comments:true"
    """
    from .modules.comments import run_comments_enrichment

    cfg = _load_config(config)
    db = _make_db(cfg)
    ai = _make_ai(cfg, command_key="comments", provider_override=ai_provider, model_override=ai_model)

    comments_cfg = cfg.get("comments", {})
    mqg_column         = comments_cfg.get("mqg_column")
    mqg_manual_column  = comments_cfg.get("mqg_manual_column")
    lcc_summary_column = comments_cfg.get("lcc_summary_column", "#lcc_summary")

    _base = cfg.get("ai", {})
    _comments_ai = {**_base, **_base.get("comments", {})}
    _effective_provider = ai_provider or _comments_ai.get("provider", "openai")
    _effective_model = ai_model or _comments_ai.get("model", "(default)")

    mode_label = "Tone Test" if tone_test else ("Dry Run" if dry_run else "Enrich")
    console.print(
        Panel(
            Text.assemble(
                ("Calibre Toolkit", "bold cyan"),
                f" — MQG-04 Comments ({mode_label})\n\n",
                ("Search:    ", "dim"),
                (search, "bold"),
                ("\nProvider:  ", "dim"),
                (f"{_effective_provider} / {_effective_model}", "bold"),
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
        tone_test=tone_test,
        mqg_column=mqg_column,
        mqg_manual_column=mqg_manual_column,
        lcc_summary_column=lcc_summary_column,
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
        typer.Option("--auto-approve", help="Auto-lock books where AI says complete + high confidence"),
    ] = False,
    ai_provider: Annotated[
        Optional[str],
        typer.Option("--ai-provider", help="Override AI provider for this run"),
    ] = None,
    ai_model: Annotated[
        Optional[str],
        typer.Option("--ai-model", help="Override AI model for this run"),
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

    Examples:

        calibre-toolkit tags-review

        calibre-toolkit tags-review "tag:Booker" --limit 20

        calibre-toolkit tags-review --no-ai --limit 50

        calibre-toolkit tags-review --auto-approve --limit 100
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
    _tags_ai = {**_base, **_base.get("tags", {})}
    _effective_provider = ai_provider or _tags_ai.get("provider", "openai")
    _effective_model    = ai_model    or _tags_ai.get("model", "(default)")

    mode_label = "Manual only" if no_ai else f"{_effective_provider} / {_effective_model}"
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
        lcc_summary_column=lcc_cfg.get("lcc_summary_column", "#lcc_summary"),
        lcc_primary_column=lcc_cfg.get("primary_class_column", "#lcc_primary_class"),
        lcc_secondary_column=lcc_cfg.get("secondary_class_column", "#lcc_secondary_class"),
        limit=limit,
        no_ai=no_ai,
        auto_approve_complete=auto_approve,
    )


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
