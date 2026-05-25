"""audit-confidence — calibration measurement loop (roadmap item 17).

Confidence tier definitions in `rules/*.md` are aspirational: a "high"
suggestion is asserted to be more accurate than "medium," but nothing
verifies the claim. This command samples applied AI suggestions from
the persistent audit log, asks the user to rate each as
correct / minor / wrong, and computes per-tier precision so the rules
become data-driven.

The command is purely observational. It does not roll back any past
write, does not modify any production code path, and does not re-call
the AI. The audit log already captures everything written; this
module reads it and turns it into a calibration session.

A "calibration session" is persisted as one JSONL line to
`~/.calibre-toolkit/calibration.jsonl`. Over time those lines form
a history of how each tier has held up.
"""

from __future__ import annotations

import json
import random
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich import box

from ..db import CalibreDB
from ..logging_config import get_logger

_log = get_logger(__name__)
console = Console()


# Rating choices presented to the user. "skipped" is recorded but
# excluded from precision math; "quit" terminates the session and
# saves whatever was rated so far.
_RATING_CHOICES = ["c", "m", "w", "s", "q"]
_RATING_LABEL = {
    "c": "correct",
    "m": "minor",
    "w": "wrong",
    "s": "skipped",
    "q": "quit",
}


# ── Data ─────────────────────────────────────────────────────────────────────


@dataclass
class AuditRecord:
    """One AI-applied write read back from `~/.calibre-toolkit/audit.log`."""

    timestamp: str
    book_id: int
    field: str
    new_value: object  # str | list[str] — varies by field
    confidence: str
    source: str
    step: str
    extra: dict = field(default_factory=dict)


@dataclass
class Rating:
    record: AuditRecord
    current_value: object
    rating: str  # "correct" | "minor" | "wrong" | "skipped"


# ── Load ─────────────────────────────────────────────────────────────────────


def load_audit_records(path: Path) -> list[AuditRecord]:
    """Read the persistent JSONL audit log; skip malformed lines.

    Filter to records that represent AI-applied writes — those have
    a non-empty `confidence`, `source`, and `step`. Manual marker
    writes (mark_mqg_complete and similar) don't carry these and
    are correctly excluded from the calibration pool.
    """
    records: list[AuditRecord] = []
    if not path.exists():
        return records
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                _log.warning("audit.log: skipping malformed JSON line")
                continue
            if not (d.get("confidence") and d.get("source") and d.get("step")):
                continue
            try:
                known = {
                    "timestamp", "book_id", "field", "new_value",
                    "confidence", "source", "step",
                }
                extra = {k: v for k, v in d.items() if k not in known}
                records.append(AuditRecord(
                    timestamp=d["timestamp"],
                    book_id=int(d["book_id"]),
                    field=d["field"],
                    new_value=d["new_value"],
                    confidence=d["confidence"],
                    source=d["source"],
                    step=d["step"],
                    extra=extra,
                ))
            except (KeyError, ValueError, TypeError):
                _log.warning("audit.log: skipping record with bad shape")
                continue
    return records


# ── Sample ───────────────────────────────────────────────────────────────────


def stratified_sample(
    records: list[AuditRecord],
    sample_size: int,
    steps_filter: list[str] | None = None,
    rng: random.Random | None = None,
) -> dict[tuple[str, str], list[AuditRecord]]:
    """Group by (step, confidence) and random-sample up to N per group.

    Stratification matters here: high-tier writes dominate volume in
    a real audit log, so a single random sample of the whole log
    would barely touch medium/low — exactly the tiers we most need
    to measure precision for.
    """
    rng = rng or random.Random()
    groups: dict[tuple[str, str], list[AuditRecord]] = {}
    for rec in records:
        if steps_filter and rec.step not in steps_filter:
            continue
        key = (rec.step, rec.confidence)
        groups.setdefault(key, []).append(rec)

    sampled: dict[tuple[str, str], list[AuditRecord]] = {}
    for key, recs in groups.items():
        if len(recs) <= sample_size:
            sampled[key] = list(recs)
        else:
            sampled[key] = rng.sample(recs, sample_size)
    return sampled


# ── Current-value lookup ─────────────────────────────────────────────────────


def fetch_current_value(db: CalibreDB, field_name: str, book_id: int):
    """Read the current Calibre value for the field, or None if missing.

    Three paths because the audit log uses different field strings
    per step:
      - lcc-enrich writes the column label directly (e.g. "#lcc",
        "#lcc_summary") so we go through get_custom_column_batch.
      - comments-enrich writes "comments" — read from the comments
        table via get_book_details_batch.
      - tags-enrich writes "tags" — get_tags_batch.
    """
    try:
        if field_name == "comments":
            details = db.get_book_details_batch([book_id])
            d = details.get(book_id)
            return d.existing_comments if d else None
        if field_name == "tags":
            return db.get_tags_batch([book_id]).get(book_id, [])
        if field_name.startswith("#"):
            return db.get_custom_column_batch([book_id], field_name).get(book_id, "")
    except Exception as e:  # noqa: BLE001 — Calibre DB layer raises Runtime/OSError
        _log.warning("current-value lookup failed for book %s field %s: %s",
                     book_id, field_name, e)
        return None
    return None


# ── Precision ────────────────────────────────────────────────────────────────


def compute_precision(
    ratings: list[Rating],
) -> dict[tuple[str, str], dict]:
    """Per (step, tier): {total, correct, minor, wrong, strict, lenient}.

    Strict precision = correct / total. Lenient = (correct + minor) / total.
    Skipped ratings are excluded entirely — they are not signal.
    """
    by_group: dict[tuple[str, str], dict[str, int]] = {}
    for r in ratings:
        if r.rating == "skipped":
            continue
        key = (r.record.step, r.record.confidence)
        d = by_group.setdefault(key, {"correct": 0, "minor": 0, "wrong": 0})
        if r.rating in d:
            d[r.rating] += 1

    out: dict[tuple[str, str], dict] = {}
    for key, counts in by_group.items():
        total = counts["correct"] + counts["minor"] + counts["wrong"]
        if total == 0:
            continue
        out[key] = {
            "total": total,
            "correct": counts["correct"],
            "minor": counts["minor"],
            "wrong": counts["wrong"],
            "strict_precision": counts["correct"] / total,
            "lenient_precision": (counts["correct"] + counts["minor"]) / total,
        }
    return out


def flag_below_threshold(
    precision_table: dict[tuple[str, str], dict],
    threshold: float,
) -> list[tuple[str, str]]:
    """Return the (step, tier) keys whose strict precision is strictly below
    the threshold. A tier exactly at the threshold is NOT flagged — the
    threshold is a floor, not a target."""
    return sorted(
        k for k, v in precision_table.items()
        if v["strict_precision"] < threshold
    )


# ── Persistence ──────────────────────────────────────────────────────────────


def persist_session(
    output_path: Path,
    session_id: str,
    threshold: float,
    ratings: list[Rating],
    precision_table: dict[tuple[str, str], dict],
    flagged: list[tuple[str, str]],
) -> None:
    """Append one session record to `~/.calibre-toolkit/calibration.jsonl`."""
    record = {
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "threshold": threshold,
        "ratings": [
            {
                "book_id": r.record.book_id,
                "field": r.record.field,
                "step": r.record.step,
                "confidence": r.record.confidence,
                "rating": r.rating,
                "audit_timestamp": r.record.timestamp,
            }
            for r in ratings
        ],
        "precision_table": {
            f"{step}|{tier}": v for (step, tier), v in precision_table.items()
        },
        "flagged": [f"{step}|{tier}" for step, tier in flagged],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Display helpers ──────────────────────────────────────────────────────────


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def _truncate(value: object, max_chars: int = 200) -> str:
    """Render any audit value as a short single-line preview."""
    if value is None:
        return "(no value)"
    if isinstance(value, list):
        s = ", ".join(str(x) for x in value)
    else:
        s = _strip_html(str(value))
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars].rstrip() + "…"


def _values_diverge(ai_value: object, current_value: object) -> bool:
    """True when the AI's logged value differs meaningfully from current.

    For list fields (tags), compare as sets — order is not meaningful.
    For strings, trim before comparison so trailing whitespace and
    rendering differences don't trigger a false 'manual override'.
    """
    if isinstance(ai_value, list) and isinstance(current_value, list):
        return {x.strip() for x in ai_value} != {x.strip() for x in current_value}
    if current_value is None:
        return True
    return str(ai_value).strip() != str(current_value).strip()


def _render_rating_prompt(
    rec: AuditRecord,
    title: str,
    authors: str,
    current_value: object,
    progress: tuple[int, int],
) -> None:
    """Display one sample for rating. Compact panel, no clutter."""
    i, total = progress
    diverged = _values_diverge(rec.new_value, current_value)
    diverged_label = (
        "  [bold yellow](current ≠ AI value — manual override)[/bold yellow]"
        if diverged else ""
    )

    console.print()
    console.rule(
        f"[bold cyan]{i}/{total}[/bold cyan]  "
        f"[bold]{title}[/bold]  [dim]{authors}[/dim]"
    )
    console.print(
        f"  Step: [bold]{rec.step}[/bold]  "
        f"Tier: [bold]{rec.confidence}[/bold]  "
        f"Field: [dim]{rec.field}[/dim]{diverged_label}"
    )
    console.print(f"  [dim]Applied:[/dim] [cyan]{_truncate(rec.new_value)}[/cyan]")
    console.print(f"  [dim]Current:[/dim] [white]{_truncate(current_value)}[/white]")


def _render_summary(
    precision_table: dict[tuple[str, str], dict],
    flagged: list[tuple[str, str]],
    threshold: float,
) -> None:
    """Show the per-(step, tier) precision table at end of session."""
    if not precision_table:
        console.print("[yellow]No ratings collected — nothing to summarise.[/yellow]")
        return

    table = Table(
        box=box.ROUNDED, show_header=True, header_style="bold cyan",
        title=f"[bold]Calibration[/bold]  [dim](threshold {threshold:.0%})[/dim]",
        title_justify="left",
    )
    table.add_column("Step",        no_wrap=True)
    table.add_column("Tier",        no_wrap=True, width=8)
    table.add_column("n",           justify="right", width=4)
    table.add_column("Correct",     justify="right", width=8)
    table.add_column("Minor",       justify="right", width=6)
    table.add_column("Wrong",       justify="right", width=6)
    table.add_column("Strict",      justify="right", width=8)
    table.add_column("Lenient",     justify="right", width=8)
    table.add_column("Flag",        no_wrap=True, width=5)

    for (step, tier) in sorted(precision_table.keys()):
        v = precision_table[(step, tier)]
        is_flagged = (step, tier) in flagged
        strict_style = "bold red" if is_flagged else "green"
        flag_str = "[bold red]⚠[/bold red]" if is_flagged else ""
        table.add_row(
            step, tier, str(v["total"]),
            str(v["correct"]), str(v["minor"]), str(v["wrong"]),
            f"[{strict_style}]{v['strict_precision']:.0%}[/{strict_style}]",
            f"{v['lenient_precision']:.0%}",
            flag_str,
        )

    console.print()
    console.print(table)
    if flagged:
        console.print(
            f"\n[bold red]{len(flagged)} tier(s) below the {threshold:.0%} "
            f"strict-precision threshold.[/bold red] "
            f"[dim]Review the rules file for that step and tier — the "
            f"definition may be aspirational rather than accurate.[/dim]"
        )
    else:
        console.print(
            f"\n[bold green]All measured tiers met the {threshold:.0%} threshold.[/bold green]"
        )


# ── Entry point ──────────────────────────────────────────────────────────────


def run_audit_confidence(
    db: CalibreDB,
    audit_log_path: Path,
    output_path: Path,
    sample_size: int = 20,
    threshold: float = 0.7,
    steps_filter: list[str] | None = None,
    seed: int | None = None,
) -> None:
    """Orchestrator: load, sample, prompt, summarise, persist."""
    rng = random.Random(seed) if seed is not None else random.Random()
    records = load_audit_records(audit_log_path)
    if not records:
        console.print(Panel(
            f"No AI-applied records found in [bold]{audit_log_path}[/bold].\n"
            "Run a step (lcc-enrich, comments-enrich, tags-enrich) and "
            "apply some suggestions first.",
            title="[yellow]Nothing to audit[/yellow]", border_style="yellow",
        ))
        return

    sampled = stratified_sample(records, sample_size, steps_filter, rng)
    if not sampled:
        console.print(Panel(
            "No records matched the requested step filter.",
            title="[yellow]Empty sample[/yellow]", border_style="yellow",
        ))
        return

    total = sum(len(recs) for recs in sampled.values())
    console.print(Panel(
        f"Sampled [bold]{total}[/bold] record(s) across "
        f"[bold]{len(sampled)}[/bold] (step, tier) group(s).\n\n"
        "For each one, compare the [bold]Applied[/bold] AI value against the "
        "[bold]Current[/bold] value in Calibre and rate:\n"
        "  [bold green]c[/bold green]orrect  · "
        "[bold yellow]m[/bold yellow]inor  · "
        "[bold red]w[/bold red]rong  · "
        "[dim]s[/dim]kip  · "
        "[dim]q[/dim]uit and save",
        title="[cyan]audit-confidence[/cyan]", border_style="cyan",
    ))

    ratings: list[Rating] = []
    quit_early = False
    idx = 0
    # Deterministic iteration order so a --seed run replays identically.
    for key in sorted(sampled.keys()):
        if quit_early:
            break
        for rec in sampled[key]:
            idx += 1
            current = fetch_current_value(db, rec.field, rec.book_id)
            title, authors = _book_label(db, rec.book_id)
            _render_rating_prompt(rec, title, authors, current, (idx, total))
            choice = Prompt.ask(
                "  Rating",
                choices=_RATING_CHOICES,
                default="s",
                show_choices=True,
            )
            label = _RATING_LABEL[choice]
            if label == "quit":
                quit_early = True
                break
            ratings.append(Rating(record=rec, current_value=current, rating=label))

    precision_table = compute_precision(ratings)
    flagged = flag_below_threshold(precision_table, threshold)
    _render_summary(precision_table, flagged, threshold)

    if ratings:
        session_id = uuid.uuid4().hex[:12]
        persist_session(
            output_path, session_id, threshold, ratings, precision_table, flagged,
        )
        console.print(
            f"\n[dim]Session [bold]{session_id}[/bold] saved to "
            f"{output_path}.[/dim]"
        )


def _book_label(db: CalibreDB, book_id: int) -> tuple[str, str]:
    """Best-effort title + authors lookup. Returns ('(deleted)', '') on miss."""
    try:
        books = db._fetch_books([book_id])
    except Exception:  # noqa: BLE001
        return ("(lookup failed)", "")
    if not books:
        return ("(deleted from library)", "")
    b = books[0]
    return (b.title, " & ".join(b.authors))
