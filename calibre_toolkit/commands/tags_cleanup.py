"""tags-cleanup — library-wide tag vocabulary normalisation.

Handler + orchestration (scanner pass → AI semantic pass → per-group bulk
approval → apply). Pure domain helpers (op grouping, scope matching, the
safe-group set) live in `modules/tags.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Annotated, TYPE_CHECKING

import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.prompt import Prompt

from datetime import datetime
from time import monotonic

from ._common import (
    app, console, DEFAULT_CONFIG_PATH,
    _load_config, _make_db, _make_ai,
)
from ..modules.tags import _group_ops, _is_safe_group, _op_touches_scope
from ..summary import StepSummary, render_summary_panel
from ..tag_scanner import scan_tags, PATTERN_GROUP_LABELS

if TYPE_CHECKING:
    from ..ai import AIClient, TagOperation
    from ..db import CalibreDB


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


def run_tags_cleanup(
    db: CalibreDB,
    ai: AIClient | None,
    min_books: int = 1,
    dry_run: bool = False,
    skip_ai: bool = False,
    search_query: str | None = None,
) -> None:
    """Two-layer tag cleanup: deterministic scanner first, then AI semantic pass.

    When `search_query` is provided, the scanner and AI pass still see
    the full library vocabulary (frequency counts are only meaningful
    library-wide), but the application loop skips operations that
    touch no book matching the search. This lets a user normalise
    vocabulary for a batch without polluting books outside that batch.
    """
    _started_at = datetime.now()
    _t0 = monotonic()

    # ── 1. Read all tags ──────────────────────────────────────────────────────
    with console.status("[cyan]Reading all tags in library…"):
        all_tags = db.get_all_tags()

    if not all_tags:
        console.print("[yellow]No tags found in library.[/yellow]")
        raise typer.Exit()

    console.print(
        f"\n[bold]Found [green]{len(all_tags)}[/green] unique tags "
        f"across the library.[/bold]"
    )

    # ── 2. Scanner pass (deterministic) ───────────────────────────────────────
    with console.status("[cyan]Running deterministic scanner…"):
        scanner_ops, handled = scan_tags(all_tags)

    console.print(
        f"[dim]Scanner: [green]{len(scanner_ops)}[/green] operation(s) on "
        f"[green]{len(handled)}[/green] tag(s).[/dim]"
    )

    # ── 3. AI semantic pass (on tags scanner didn't touch) ────────────────────
    ai_ops: list[TagOperation] = []
    if not skip_ai and ai is not None:
        remaining = [(t, c) for t, c in all_tags if t not in handled and c >= min_books]
        if remaining:
            batch_size = 150
            total_batches = (len(remaining) + batch_size - 1) // batch_size
            console.print(
                f"[dim]AI semantic analysis on [cyan]{len(remaining)}[/cyan] tag(s) "
                f"in [cyan]{total_batches}[/cyan] batch(es) of [cyan]{batch_size}[/cyan] "
                f"([cyan]{ai.max_concurrency}[/cyan] in flight)…[/dim]"
            )
            from rich.progress import (
                Progress, SpinnerColumn, TextColumn, BarColumn,
                MofNCompleteColumn, TimeElapsedColumn,
            )
            with Progress(
                SpinnerColumn(),
                TextColumn("[cyan]Batches"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                TextColumn("[red]{task.fields[failed]} failed"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("ai", total=total_batches, failed=0)

                def _on_progress(done: int, total: int, failed: int) -> None:
                    progress.update(task, completed=done, failed=failed)

                try:
                    ai_ops = ai.suggest_tag_cleanup(
                        remaining,
                        batch_size=batch_size,
                        progress_callback=_on_progress,
                    )
                except RuntimeError as e:
                    console.print(Panel(
                        str(e), title="[red]AI analysis failed[/red]",
                        border_style="red",
                    ))
                    raise typer.Exit(1)
            failed = len(getattr(ai, "last_failures", []) or [])
            console.print(
                f"[dim]AI: [green]{len(ai_ops)}[/green] operation(s) proposed"
                + (f"; [red]{failed}[/red] batch(es) failed" if failed else "")
                + ".[/dim]"
            )

    all_ops = scanner_ops + ai_ops
    if not all_ops:
        console.print(
            "\n[green]No cleanup operations proposed — vocabulary looks clean.[/green]"
        )
        return

    # ── 3b. Scope filter (item 18) ────────────────────────────────────────────
    # Library-wide path: search_query is None → no filtering, all_ops applied.
    # Scoped path: ops whose source_tags do not appear on any in-scope book
    # are silently dropped before display, so the user only reviews work
    # that will actually touch their batch.
    if search_query:
        total_before = len(all_ops)
        with console.status(f"[cyan]Resolving scope:[/] {search_query}"):
            try:
                scope_books = db.search(search_query)
            except RuntimeError as e:
                console.print(Panel(
                    str(e), title="[red]Scope search failed[/red]", border_style="red",
                ))
                raise typer.Exit(1)
            scope_book_ids = [b.id for b in scope_books]
            scope_tags = db.get_tags_for_books(scope_book_ids)

        all_ops = [op for op in all_ops if _op_touches_scope(op, scope_tags)]
        console.print(
            f"[dim]Scope:[/dim] [bold]{search_query}[/bold]  "
            f"[dim]matched[/dim] [bold]{len(scope_book_ids)}[/bold] [dim]book(s);[/dim] "
            f"[bold]{len(all_ops)}[/bold] [dim]of[/dim] [bold]{total_before}[/bold] "
            f"[dim]op(s) in scope ([bold]{total_before - len(all_ops)}[/bold] skipped).[/dim]"
        )
        if not all_ops:
            console.print(
                "\n[green]No cleanup operations affect books in scope — "
                "nothing to do.[/green]"
            )
            return

    # ── 4. Group operations by pattern_group and display ──────────────────────
    grouped = _group_ops(all_ops)

    console.print(
        f"\n[bold]{len(all_ops)} operation(s) across "
        f"{len(grouped)} pattern group(s):[/bold]\n"
    )
    for group_key in grouped:
        _display_pattern_group(group_key, grouped[group_key])

    if dry_run:
        console.print("\n[dim]Dry-run — no changes written.[/dim]")
        proposed_by_pattern_group: dict[str, int] = {}
        for op in all_ops:
            proposed_by_pattern_group[op.pattern_group] = (
                proposed_by_pattern_group.get(op.pattern_group, 0) + 1
            )
        console.print(render_summary_panel(
            StepSummary(
                step_label="tags-cleanup",
                started_at=_started_at,
                elapsed_seconds=monotonic() - _t0,
                extras={"by_pattern_group": proposed_by_pattern_group},
                usage=ai.usage if ai is not None else None,
            ),
            dry_run=True,
        ))
        return

    # ── 5. Per-group bulk approval ────────────────────────────────────────────
    to_apply: list[TagOperation] = []
    for group_key, ops in grouped.items():
        label = PATTERN_GROUP_LABELS.get(group_key, group_key)
        default = "all" if _is_safe_group(group_key) else "review"
        console.print("[dim]Waiting for input…[/dim]")
        choice = Prompt.ask(
            f"\n[bold]{label}[/bold] — {len(ops)} op(s). Apply?  \\[a]ll / \\[e]xcept / \\[r]eview / \\[s]kip",
            choices=["all", "except", "review", "skip", "a", "e", "r", "s"],
            default=default,
            show_choices=False,
        )
        choice = {"a": "all", "e": "except", "r": "review", "s": "skip"}.get(choice, choice)
        if choice == "all":
            to_apply.extend(ops)
        elif choice == "except":
            to_apply.extend(_apply_all_except(ops))
        elif choice == "review":
            to_apply.extend(_review_ops_individually(ops))

    if not to_apply:
        console.print("\n[dim]No operations approved. Nothing changed.[/dim]")
        console.print(render_summary_panel(
            StepSummary(
                step_label="tags-cleanup",
                started_at=_started_at,
                elapsed_seconds=monotonic() - _t0,
                usage=ai.usage if ai is not None else None,
            ),
        ))
        return

    # ── 6. Apply ──────────────────────────────────────────────────────────────
    total_affected, by_pattern_group, _errors = _apply_operations(db, to_apply)

    extras: dict[str, dict[str, int]] = {}
    if by_pattern_group:
        extras["by_pattern_group"] = by_pattern_group
    if total_affected:
        extras["links_changed"] = {"book-tag links": total_affected}

    console.print(render_summary_panel(
        StepSummary(
            step_label="tags-cleanup",
            started_at=_started_at,
            elapsed_seconds=monotonic() - _t0,
            extras=extras,
            usage=ai.usage if ai is not None else None,
        ),
    ))


def _display_pattern_group(group_key: str, ops: list[TagOperation]) -> None:
    """Show a summary panel + examples for one pattern group."""
    label = PATTERN_GROUP_LABELS.get(group_key, group_key)
    total_books = sum(op.book_count for op in ops)

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
        show_lines=False,
        title=f"[bold]{label}[/bold]  "
              f"[dim]({len(ops)} op(s), {total_books} book(s) affected)[/dim]",
        title_justify="left",
    )
    table.add_column("#", width=4, no_wrap=True, justify="right", style="dim")
    table.add_column("Kind",  width=8, no_wrap=True)
    table.add_column("Change", ratio=5)
    table.add_column("Books", width=7, no_wrap=True, justify="right")
    table.add_column("Reason", ratio=3, style="dim")

    for idx, op in enumerate(ops, start=1):
        kind_style = {
            "drop":   "red",
            "merge":  "yellow",
            "rename": "cyan",
            "split":  "magenta",
        }.get(op.kind, "white")
        table.add_row(
            str(idx),
            Text(op.kind, style=kind_style),
            op.display_arrow,
            str(op.book_count),
            op.reason,
        )
    console.print(table)


def _apply_all_except(ops: list[TagOperation]) -> list[TagOperation]:
    """Apply every op except the indices the user excludes (1-based, as shown)."""
    while True:
        raw = Prompt.ask(
            f"  Exclude which row #(s)? (comma/space separated, 1–{len(ops)}, "
            f"or blank to apply all)",
            default="",
        ).strip()
        if not raw:
            return list(ops)
        tokens = [t for t in raw.replace(",", " ").split() if t]
        try:
            excluded = {int(t) for t in tokens}
        except ValueError:
            console.print("  [red]Could not parse — please enter numbers only.[/red]")
            continue
        bad = [n for n in excluded if n < 1 or n > len(ops)]
        if bad:
            console.print(f"  [red]Out of range: {bad}. Try again.[/red]")
            continue
        approved = [op for idx, op in enumerate(ops, start=1) if idx not in excluded]
        console.print(
            f"  [dim]Excluding {len(excluded)} op(s); applying {len(approved)}.[/dim]"
        )
        if excluded:
            for n in sorted(excluded):
                console.print(f"    [dim]✗ #{n}: {ops[n - 1].display_arrow}[/dim]")
        return approved


def _review_ops_individually(ops: list[TagOperation]) -> list[TagOperation]:
    """Walk through ops one at a time. Returns approved subset."""
    approved: list[TagOperation] = []
    for op in ops:
        console.rule()
        console.print(f"  [bold]{op.kind.upper()}[/bold]  {op.display_arrow}")
        console.print(f"  Books: {op.book_count}")
        console.print(f"  [dim]{op.reason}[/dim]")
        choice = Prompt.ask(
            "  Apply?", choices=["y", "n"], default="y",
            show_choices=True, show_default=True,
        )
        if choice == "y":
            approved.append(op)
        else:
            console.print("  [dim]Skipped.[/dim]")
    return approved


def _apply_operations(
    db: CalibreDB,
    ops: list[TagOperation],
) -> tuple[int, dict[str, int], list[str]]:
    """Execute approved operations via direct SQLite tag-table writes.

    Each op touches the tags / books_tags_link tables directly — no
    per-book subprocess calls. One SQL statement per source tag regardless
    of how many books carry it.

    Returns (total_affected_links, ops_by_pattern_group, errors). The
    caller is responsible for rendering the end-of-run StepSummary; this
    function only prints per-op progress and the error list.
    """
    total_affected = 0
    errors: list[str] = []
    by_pattern_group: dict[str, int] = {}

    for i, op in enumerate(ops, 1):
        try:
            count = 0
            if not op.target_tags:
                # DROP: remove each source tag from all books
                for src in op.source_tags:
                    count += db.drop_tag(src)
            else:
                # RENAME / MERGE: fold each source into the single target
                target = op.target_tags[0]
                for src in op.source_tags:
                    count += db.rename_tag(src, target)

            total_affected += count
            by_pattern_group[op.pattern_group] = by_pattern_group.get(op.pattern_group, 0) + 1
            console.print(
                f"  [green]✓[/green] {op.display_arrow}  "
                f"[dim]({count} book(s))[/dim]"
            )
        except Exception as e:
            errors.append(f"{op.display_arrow}: {e}")
            console.print(f"  [red]✗[/red] {op.display_arrow}: {e}")

    if errors:
        console.print(f"[red]{len(errors)} error(s) during apply:[/red]")
        for err in errors[:10]:
            console.print(f"  [red]✗[/red] {err}")
        if len(errors) > 10:
            console.print(f"  [dim]… + {len(errors) - 10} more[/dim]")

    return total_affected, by_pattern_group, errors
