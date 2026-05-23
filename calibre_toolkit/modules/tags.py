"""
MQG-05 Tags Enrichment module.
Orchestrates: read current tags + LCC context → AI propose → display → confirm → write.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.prompt import Prompt

from ..ai import AIClient, TagsSuggestion, TagOperation
from ..db import CalibreDB
from ..tag_scanner import scan_tags, PATTERN_GROUP_LABELS

console = Console()

_CONF_DISPLAY = {
    "high":   ("●", "green"),
    "medium": ("◐", "yellow"),
    "low":    ("○", "red"),
}


def _build_review_table(suggestions: list[TagsSuggestion]) -> Table:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
                  expand=True, show_lines=True)
    table.add_column("#",       style="dim", width=4, no_wrap=True)
    table.add_column("Conf",    width=5, no_wrap=True)
    table.add_column("Book",    ratio=2)
    table.add_column("Tags",    ratio=5)

    for i, s in enumerate(suggestions, 1):
        icon, style = _CONF_DISPLAY.get(s.confidence, ("—", "dim"))

        book_text = Text()
        book_text.append(s.title)
        book_text.append(f"\n{s.authors_display}", style="dim")

        tags_text = _format_tags_diff(s)

        table.add_row(str(i), Text(icon, style=style), book_text, tags_text)

    return table


def _format_tags_diff(s: TagsSuggestion) -> Text:
    """Render kept/added/removed tags with colour coding in a single cell."""
    t = Text()
    kept_lower = {x.lower() for x in s.kept}
    removed_lower = {x.lower() for x in s.removed}

    parts: list[tuple[str, str]] = []

    # Kept tags — dim (already had them, no change)
    for tag in s.kept:
        parts.append((tag, "dim"))

    # Added tags — bold green (new)
    for tag in s.added:
        parts.append((f"+ {tag}", "bold green"))

    # Removed tags — red (being dropped)
    for tag in s.removed:
        parts.append((f"- {tag}", "red"))

    for idx, (label, color) in enumerate(parts):
        t.append(label, style=color)
        if idx < len(parts) - 1:
            t.append("  ", style="dim")

    if s.notes:
        t.append(f"\n↳ {s.notes}", style="dim italic")

    if not parts:
        t.append("(no change)", style="dim")

    return t


def run_tags_enrichment(
    db: CalibreDB,
    ai: AIClient,
    search_query: str,
    batch_size: int = 20,
    limit: int | None = None,
    dry_run: bool = False,
    mqg_column: str | None = None,
    mqg_manual_column: str | None = None,
    lcc_summary_column: str | None = None,
    lcc_secondary_column: str | None = None,
    lcc_primary_column: str | None = None,
) -> None:
    """Full MQG-05 Tags enrichment flow for a Calibre search string."""

    # ── 1. Search ─────────────────────────────────────────────────────────────
    effective_query = (
        f"({search_query}) and not {mqg_manual_column}:true"
        if mqg_manual_column else search_query
    )
    try:
        with console.status(f"[cyan]Searching library:[/] {search_query}"):
            books = db.search(effective_query)
    except RuntimeError as e:
        console.print(Panel(str(e), title="[red]Cannot access library[/red]", border_style="red"))
        raise typer.Exit(1)

    if not books:
        console.print("[yellow]No books matched that search. Nothing to do.[/yellow]")
        raise typer.Exit()

    total_matched = len(books)
    if limit and len(books) > limit:
        books = books[:limit]
        console.print(
            f"\n[bold]Found [green]{total_matched}[/green] books "
            f"— processing first [cyan]{limit}[/cyan] (--limit).[/bold]"
        )
    else:
        console.print(f"\n[bold]Found [green]{len(books)}[/green] books.[/bold]")

    # ── 2. Read current tags and LCC context ──────────────────────────────────
    book_ids = [b.id for b in books]
    with console.status("[cyan]Reading current tags and LCC context…"):
        tags_map = db.get_tags_batch(book_ids)
        context_map: dict[int, dict[str, str]] = {bid: {} for bid in book_ids}
        for col_key, col_label in [
            ("lcc_summary",        lcc_summary_column),
            ("lcc_secondary_class", lcc_secondary_column),
            ("lcc_primary_class",   lcc_primary_column),
        ]:
            if col_label:
                batch = db.get_custom_column_batch(book_ids, col_label)
                for bid, val in batch.items():
                    context_map[bid][col_key] = val

    # ── 3. AI generation ───────────────────────────────────────────────────────
    with console.status(
        f"[cyan]Generating tags for {len(books)} book(s) "
        f"in batches of {batch_size}…[/cyan]"
    ):
        try:
            suggestions = ai.suggest_tags(books, tags_map, context_map, batch_size=batch_size)
        except RuntimeError as e:
            console.print(Panel(str(e), title="[red]AI generation failed[/red]", border_style="red"))
            raise typer.Exit(1)

    if not suggestions:
        console.print("[yellow]AI returned no suggestions.[/yellow]")
        raise typer.Exit(1)

    high   = [s for s in suggestions if s.confidence == "high"]
    medium = [s for s in suggestions if s.confidence == "medium"]
    low    = [s for s in suggestions if s.confidence == "low"]

    console.print(
        f"\n[bold]Results:[/bold] "
        f"[green]{len(high)} high[/green], "
        f"[yellow]{len(medium)} medium[/yellow], "
        f"[red]{len(low)} low[/red]\n"
    )

    # ── 4. Dry-run or display review table ────────────────────────────────────
    if dry_run:
        console.print("[bold cyan]── Dry-run: proposed tags (no writes) ──[/bold cyan]\n")
        console.print(_build_review_table(suggestions))
        changed = sum(1 for s in suggestions if s.tags_changed)
        console.print(
            f"\n[dim]Dry-run complete — {len(suggestions)} book(s) shown, "
            f"{changed} would change. No writes.[/dim]"
        )
        return

    console.print(_build_review_table(suggestions))
    console.print(
        "\n[dim]Legend: [green]●[/green] high  [yellow]◐[/yellow] medium  [red]○[/red] low  "
        "│  [dim]dim[/dim] = kept  [bold green]+ green[/bold green] = added  "
        "[red]- red[/red] = removed[/dim]\n"
    )

    # ── 5. Apply ───────────────────────────────────────────────────────────────
    applied_ids: list[int] = []
    declined: list[TagsSuggestion] = []

    if high:
        choice = Prompt.ask(
            f"\n[bold]Tier 1:[/bold] Apply {len(high)} high-confidence "
            f"tag set{'s' if len(high) != 1 else ''}?",
            choices=["all", "review", "skip"], default="all", show_choices=True,
        )
        if choice == "all":
            applied_ids += _apply_batch(db, high)
        elif choice == "review":
            a, d = _prompt_and_apply(db, high)
            applied_ids += a
            declined += d

    if medium:
        choice = Prompt.ask(
            f"\n[bold yellow]Tier 2:[/bold yellow] Apply {len(medium)} medium-confidence "
            f"tag set{'s' if len(medium) != 1 else ''}?",
            choices=["all", "review", "skip"], default="review", show_choices=True,
        )
        if choice == "all":
            applied_ids += _apply_batch(db, medium)
        elif choice == "review":
            a, d = _prompt_and_apply(db, medium)
            applied_ids += a
            declined += d

    if low:
        choice = Prompt.ask(
            f"\n[bold red]Tier 3:[/bold red] Apply {len(low)} low-confidence "
            f"tag set{'s' if len(low) != 1 else ''}?",
            choices=["all", "review", "skip"], default="skip", show_choices=True,
        )
        if choice == "all":
            applied_ids += _apply_batch(db, low)
        elif choice == "review":
            a, d = _prompt_and_apply(db, low)
            applied_ids += a
            declined += d
        else:
            declined += low

    # ── 6. Mark MQG ───────────────────────────────────────────────────────────
    high_applied = [s.book_id for s in high if s.book_id in applied_ids]
    if mqg_column and high_applied:
        _mark_complete(db, mqg_column, high_applied, label="MQG-05")

    manual_ids = [s.book_id for s in declined]
    if mqg_manual_column and manual_ids:
        console.print(
            f"\n[yellow]Flagging {len(manual_ids)} book(s)[/yellow] in "
            f"[bold]{mqg_manual_column}[/bold] for manual review."
        )
        with console.status("Flagging…"):
            db.mark_mqg_complete(manual_ids, mqg_manual_column)

    console.print(
        f"\n[bold green]Done![/bold green] "
        f"[green]{len(applied_ids)}[/green] applied, "
        f"[green]{len(high_applied)}[/green] marked MQG-05 complete"
        + (f", [yellow]{len(manual_ids)}[/yellow] flagged for manual" if manual_ids else "")
        + "."
    )


def _apply_batch(db: CalibreDB, suggestions: list[TagsSuggestion]) -> list[int]:
    applied: list[int] = []
    for s in suggestions:
        with console.status(f"Writing tags for book {s.book_id}…"):
            try:
                db.apply_tags(s.book_id, s.proposed_tags)
                applied.append(s.book_id)
            except RuntimeError as e:
                console.print(f"[red]Error on book {s.book_id}: {e}[/red]")
    console.print(f"[green]Applied {len(applied)}/{len(suggestions)} tag sets.[/green]")
    return applied


def _prompt_and_apply(
    db: CalibreDB,
    suggestions: list[TagsSuggestion],
) -> tuple[list[int], list[TagsSuggestion]]:
    to_apply: list[TagsSuggestion] = []
    declined: list[TagsSuggestion] = []

    for s in suggestions:
        console.rule(f"[bold]Book {s.book_id}[/bold]")
        console.print(f"  [bold]{s.title}[/bold]  [dim]{s.authors_display}[/dim]")
        icon, style = _CONF_DISPLAY.get(s.confidence, ("—", "dim"))
        console.print(f"  Confidence: [{style}]{icon} {s.confidence}[/{style}]")
        if s.kept:
            console.print(f"  Kept:     [dim]{', '.join(s.kept)}[/dim]")
        if s.added:
            console.print(f"  Added:    [bold green]{', '.join(s.added)}[/bold green]")
        if s.removed:
            console.print(f"  Removed:  [red]{', '.join(s.removed)}[/red]")
        if s.notes:
            console.print(f"  [dim]{s.notes}[/dim]")

        default = "n" if s.confidence == "low" else "y"
        choice = Prompt.ask(
            "  Apply?", choices=["y", "n"], default=default,
            show_choices=True, show_default=True,
        )
        if choice == "y":
            to_apply.append(s)
        else:
            declined.append(s)
            console.print("  [dim]Declined — will be flagged for manual review.[/dim]")

    applied = _apply_batch(db, to_apply) if to_apply else []
    return applied, declined


def run_tags_cleanup(
    db: CalibreDB,
    ai: AIClient | None,
    min_books: int = 1,
    dry_run: bool = False,
    skip_ai: bool = False,
) -> None:
    """Two-layer tag cleanup: deterministic scanner first, then AI semantic pass."""

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
        return

    # ── 5. Per-group bulk approval ────────────────────────────────────────────
    to_apply: list[TagOperation] = []
    for group_key, ops in grouped.items():
        label = PATTERN_GROUP_LABELS.get(group_key, group_key)
        default = "all" if _is_safe_group(group_key) else "review"
        choice = Prompt.ask(
            f"\n[bold]{label}[/bold] — {len(ops)} op(s). Apply?",
            choices=["all", "except", "review", "skip"],
            default=default,
            show_choices=True,
        )
        if choice == "all":
            to_apply.extend(ops)
        elif choice == "except":
            to_apply.extend(_apply_all_except(ops))
        elif choice == "review":
            to_apply.extend(_review_ops_individually(ops))

    if not to_apply:
        console.print("\n[dim]No operations approved. Nothing changed.[/dim]")
        return

    # ── 6. Apply ──────────────────────────────────────────────────────────────
    _apply_operations(db, to_apply)


def _group_ops(ops: list[TagOperation]) -> dict[str, list[TagOperation]]:
    """Group operations by pattern_group, preserving a sensible display order."""
    order = [
        "formatting",
        "garbage",
        "bisac-code",
        "calibre-taxonomy",
        "date-range-lookup",
        "lcsh-bare-date-range",
        "lcsh-date-subject",
        "lcsh-chain",
        "ai-semantic",
    ]
    grouped: dict[str, list[TagOperation]] = {}
    for op in ops:
        grouped.setdefault(op.pattern_group, []).append(op)
    # Sort: known groups in defined order, unknown groups last alphabetically
    result: dict[str, list[TagOperation]] = {}
    for key in order:
        if key in grouped:
            result[key] = grouped.pop(key)
    for key in sorted(grouped):
        result[key] = grouped[key]
    return result


def _is_safe_group(group_key: str) -> bool:
    """Pattern groups that default to 'apply all' rather than review."""
    return group_key in {
        "formatting",
        "garbage",
        "bisac-code",
        "calibre-taxonomy",
        "date-range-lookup",
        "lcsh-bare-date-range",
        "lcsh-date-subject",
        "lcsh-chain",
    }


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


def _apply_operations(db: CalibreDB, ops: list[TagOperation]) -> None:
    """Execute approved operations via direct SQLite tag-table writes.

    Each op touches the tags / books_tags_link tables directly — no
    per-book subprocess calls. One SQL statement per source tag regardless
    of how many books carry it.
    """
    total_affected = 0
    errors: list[str] = []

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
            console.print(
                f"  [green]✓[/green] {op.display_arrow}  "
                f"[dim]({count} book(s))[/dim]"
            )
        except Exception as e:
            errors.append(f"{op.display_arrow}: {e}")
            console.print(f"  [red]✗[/red] {op.display_arrow}: {e}")

    console.print(
        f"\n[bold green]Done![/bold green] "
        f"{len(ops)} operation(s), {total_affected} book-tag link(s) changed."
    )
    if errors:
        console.print(f"[red]{len(errors)} error(s) during apply:[/red]")
        for err in errors[:10]:
            console.print(f"  [red]✗[/red] {err}")
        if len(errors) > 10:
            console.print(f"  [dim]… + {len(errors) - 10} more[/dim]")


def _mark_complete(
    db: CalibreDB, mqg_column: str, book_ids: list[int], label: str
) -> None:
    if not mqg_column or not book_ids:
        return
    with console.status(f"[cyan]Marking {len(book_ids)} books as {label} complete…"):
        db.mark_mqg_complete(book_ids, mqg_column)
    console.print(
        f"[dim]Marked {len(book_ids)} books complete in [bold]{mqg_column}[/bold].[/dim]"
    )
