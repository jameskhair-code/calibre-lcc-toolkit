"""regrade — re-run an enrichment step on books made stale by a rule change.

When you edit a rule (e.g. `rules/lcc.md`) to fix a calibration miss, every AI
write made before that edit is stale relative to the new rule. This command
finds the affected books from the audit log and re-runs just those against the
new prompt, reusing each step's existing run path with an explicit book-id list.

Key design points (v1.8 PR 6):

- **Staleness is keyed off a timestamp cutoff, not a session.** The audit log
  has no session marker; the operator supplies `--before <date>` (the date the
  rule changed). A book is stale when its *latest* audit entry for the step
  predates the cutoff — a book already re-graded after the cutoff drops out, so
  it is never re-graded twice.
- **Re-grade writes are marked.** The run executes inside `regrade_audit`, so
  every resulting audit entry carries `regrade=<cutoff>` and is excluded from
  calibration (it re-runs a changed rule, so counting it as an original write
  would mix pre- and post-change accuracy).
- **Manual flags are respected.** Re-grade bypasses Calibre search, so it must
  re-apply the steps' `not <manual>:true` exclusion itself. Manually-curated
  books are skipped by default; `--force` includes them.
- **Reuses the PR 4 reader** (`read_audit_entries`/`filter_entries`) — no
  second parser.

Scope: the three audited, rule-driven steps — lcc-enrich, comments-enrich,
tags-enrich. clean-titles and enrich-identifiers write no audit trail, so their
stale books can't be found this way.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from ..db import CalibreDB
from ..logging_config import get_logger, regrade_audit
from .audit_log import read_audit_entries, filter_entries, _parse_ts

_log = get_logger(__name__)
console = Console()

STEPS = ("lcc-enrich", "comments-enrich", "tags-enrich")


def find_stale_books(entries: list[dict], step: str, before: datetime) -> list[int]:
    """Book IDs whose latest audit entry for `step` predates `before`.

    Aggregates to the latest entry per book (across original and any prior
    re-grade writes) so a book already re-graded after the cutoff is excluded.
    Builds on the shared `filter_entries`.
    """
    step_entries = filter_entries(entries, step=step)
    latest: dict[int, datetime] = {}
    for d in step_entries:
        ts = _parse_ts(d.get("timestamp"))
        raw = d.get("book_id")
        if ts is None or raw is None:
            continue
        try:
            bid = int(raw)
        except (TypeError, ValueError):
            continue
        if bid not in latest or ts > latest[bid]:
            latest[bid] = ts
    return sorted(bid for bid, ts in latest.items() if ts < before)


def _manual_column(cfg: dict, step: str) -> str | None:
    """The manual-review column for a step, resolved the way each command does
    (the config location differs per step)."""
    if step == "lcc-enrich":
        return cfg.get("mqg", {}).get("lcc_manual_column")
    if step == "comments-enrich":
        return cfg.get("comments", {}).get("mqg_manual_column")
    if step == "tags-enrich":
        return cfg.get("tags", {}).get("mqg_manual_column")
    return None


def run_regrade(
    db: CalibreDB,
    ai,
    cfg: dict,
    *,
    step: str,
    before: datetime,
    before_label: str,
    audit_path: Path,
    dry_run: bool,
    force: bool,
    limit: int | None,
    apply_confirm_threshold: int,
) -> None:
    """Select stale books for `step` and re-run them against the current rule.

    `before_label` is the raw cutoff string the operator gave; it becomes the
    `regrade` audit marker so a later analysis knows which rule-boundary the
    re-grade ran against.
    """
    entries = read_audit_entries(audit_path)
    stale = find_stale_books(entries, step, before)

    if not stale:
        console.print(Panel(
            f"No [bold]{step}[/bold] writes predate [bold]{before_label}[/bold] "
            f"in {audit_path}.\nNothing to re-grade.",
            title="[yellow]No stale writes[/yellow]", border_style="yellow",
        ))
        return

    manual_column = _manual_column(cfg, step)
    skipped_manual: list[int] = []
    if manual_column and not force:
        try:
            flagged = set(db._search_ids(f"{manual_column}:true"))
        except RuntimeError as e:
            console.print(Panel(str(e), title="[red]Cannot access library[/red]",
                                border_style="red"))
            raise typer.Exit(1)
        skipped_manual = [b for b in stale if b in flagged]
        stale = [b for b in stale if b not in flagged]

    capped = bool(limit and len(stale) > limit)
    if capped:
        stale = stale[:limit]

    console.print(
        f"\n[bold]{len(stale)}[/bold] book(s) stale for [bold]{step}[/bold] "
        f"before [bold]{before_label}[/bold]."
    )
    if skipped_manual:
        console.print(
            f"[dim]Skipped {len(skipped_manual)} manually-curated book(s) "
            f"({manual_column}); use --force to include them.[/dim]"
        )
    if capped:
        console.print(f"[dim]Capped to first {limit} (--limit).[/dim]")

    if dry_run:
        preview = ", ".join(str(b) for b in stale[:50])
        more = "" if len(stale) <= 50 else f" … (+{len(stale) - 50} more)"
        console.print(f"[dim]Book ids:[/dim] {preview}{more}")
        console.print("\n[bold cyan]── Dry-run: no books re-graded ──[/bold cyan]")
        return

    if not stale:
        console.print("[green]Nothing to re-grade after manual-flag exclusion.[/green]")
        return

    # Every audit_log call inside this scope is tagged regrade=<cutoff>.
    with regrade_audit(before_label):
        _dispatch(db, ai, cfg, step, stale, apply_confirm_threshold)


def _dispatch(
    db: CalibreDB,
    ai,
    cfg: dict,
    step: str,
    book_ids: list[int],
    apply_confirm_threshold: int,
) -> None:
    """Invoke the step's existing run function with the explicit book-id list."""
    if step == "lcc-enrich":
        import os
        from ..modules.lcc import run_lcc_enrichment
        lcc_cfg = cfg.get("lcc", {})
        columns = {
            "lcc": lcc_cfg.get("lcc_column", "#lcc"),
            "lcc_primary_class": lcc_cfg.get("primary_class_column", "#lcc_primary_class"),
            "lcc_secondary_class": lcc_cfg.get("secondary_class_column", "#lcc_secondary_class"),
            "lcc_summary": lcc_cfg.get("lcc_summary_column", "#lcc_summary"),
        }
        catalog_cfg = cfg.get("catalog", {})
        description_cfg = cfg.get("description", {})
        google_books_api_key = (
            os.environ.get("GOOGLE_BOOKS_API_KEY")
            or description_cfg.get("google_books_api_key", "")
        ) or None
        run_lcc_enrichment(
            db=db, ai=ai, search_query="", columns=columns,
            mqg_column=cfg.get("mqg", {}).get("lcc_column"),
            mqg_manual_column=cfg.get("mqg", {}).get("lcc_manual_column"),
            catalog_timeout=float(catalog_cfg.get("request_timeout_seconds", 10.0)),
            catalog_max_retries=int(catalog_cfg.get("max_retries", 3)),
            description_timeout=float(description_cfg.get(
                "request_timeout_seconds", catalog_cfg.get("request_timeout_seconds", 10.0))),
            description_max_retries=int(description_cfg.get(
                "max_retries", catalog_cfg.get("max_retries", 3))),
            google_books_api_key=google_books_api_key,
            apply_confirm_threshold=apply_confirm_threshold,
            book_ids=book_ids,
        )
    elif step == "comments-enrich":
        from ..modules.comments import run_comments_enrichment
        comments_cfg = cfg.get("comments", {})
        run_comments_enrichment(
            db=db, ai=ai, search_query="",
            mqg_column=comments_cfg.get("mqg_column"),
            mqg_manual_column=comments_cfg.get("mqg_manual_column"),
            lcc_summary_column=comments_cfg.get("lcc_summary_column", "#lcc_summary"),
            apply_confirm_threshold=apply_confirm_threshold,
            book_ids=book_ids,
        )
    elif step == "tags-enrich":
        from ..modules.tags import run_tags_enrichment
        tags_cfg = cfg.get("tags", {})
        lcc_cfg = cfg.get("lcc", {})
        run_tags_enrichment(
            db=db, ai=ai, search_query="",
            mqg_column=tags_cfg.get("mqg_column"),
            mqg_manual_column=tags_cfg.get("mqg_manual_column"),
            lcc_summary_column=lcc_cfg.get("lcc_summary_column", "#lcc_summary"),
            lcc_secondary_column=lcc_cfg.get("secondary_class_column", "#lcc_secondary_class"),
            lcc_primary_column=lcc_cfg.get("primary_class_column", "#lcc_primary_class"),
            apply_confirm_threshold=apply_confirm_threshold,
            book_ids=book_ids,
        )
