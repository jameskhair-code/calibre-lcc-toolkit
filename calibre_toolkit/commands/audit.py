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
    """Read the persistent JSONL audit log as calibration records.

    Builds on the shared `read_audit_entries` reader (one parser for the
    whole toolkit), then filters to records that represent AI-applied writes
    — those have a non-empty `confidence`, `source`, and `step`. Manual marker
    writes (mark_mqg_complete and similar) don't carry these and are correctly
    excluded from the calibration pool. Re-grade writes (carrying a `regrade`
    marker) are also excluded — they re-run a changed rule and would otherwise
    mix pre- and post-change accuracy in the same tier stats.
    """
    # Deferred import: pulling in .audit_log at module top would register its
    # audit-log CLI handler before this module's audit-confidence handler,
    # reordering the command listing in `calibre-toolkit --help`.
    from .audit_log import read_audit_entries

    records: list[AuditRecord] = []
    for d in read_audit_entries(path):
        if not (d.get("confidence") and d.get("source") and d.get("step")):
            continue
        if d.get("regrade"):
            # Re-grade writes are re-runs against a changed rule; counting them
            # as original writes would mix pre- and post-rule accuracy in the
            # same tier stats. Excluded from calibration (v1.8 PR 6).
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


# Grading order priority. High-tier writes dominate volume and are the
# quickest to rate, so surfacing them first lets signal accrue before the
# session ends. Unknown tiers sort last.
_TIER_PRIORITY = {"high": 0, "medium": 1, "low": 2}


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


def grading_order(
    sampled: dict[tuple[str, str], list[AuditRecord]],
) -> list[tuple[tuple[str, str], AuditRecord]]:
    """Flatten sampled groups into grading order: high tier first, then
    medium, then low; step alphabetical within a tier; original sample
    order within a group. Deterministic so a --seed run replays identically.
    """
    ordered_keys = sorted(
        sampled.keys(),
        key=lambda k: (_TIER_PRIORITY.get(k[1], 99), k[0]),
    )
    flat: list[tuple[tuple[str, str], AuditRecord]] = []
    for key in ordered_keys:
        for rec in sampled[key]:
            flat.append((key, rec))
    return flat


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


def persist_rule_revisions(
    path: Path,
    session_id: str,
    threshold: float,
    entries: list[tuple[str, str, float, str]],
) -> None:
    """Append rule-revision intents to rule-revisions.jsonl, one line each.

    `entries` are (step, tier, strict_precision, note). This is a capture
    buffer for a future architect pass — accumulated signal about which tier
    definitions drifted and what the maintainer would change. Nothing reads
    it automatically yet.
    """
    if not entries:
        return
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for step, tier, strict, note in entries:
            f.write(json.dumps({
                "timestamp": ts,
                "session_id": session_id,
                "step": step,
                "tier": tier,
                "strict_precision": strict,
                "threshold": threshold,
                "note": note,
            }, ensure_ascii=False) + "\n")


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


def _prompt_rule_revisions(
    flagged: list[tuple[str, str]],
    precision_table: dict[tuple[str, str], dict],
) -> list[tuple[str, str, float, str]]:
    """Ask, per flagged tier, what the maintainer would change in the rule.

    Empty answers are dropped. Returns (step, tier, strict, note) entries
    for persistence. Interactive — exercised manually, not in the suite.
    """
    console.print(
        "\n[bold]Capture rule-revision intent[/bold] for the flagged tier(s). "
        "[dim]Press enter to skip a tier.[/dim]"
    )
    entries: list[tuple[str, str, float, str]] = []
    for (step, tier) in flagged:
        strict = precision_table[(step, tier)]["strict_precision"]
        note = Prompt.ask(
            f"  [bold]{step}[/bold]/[bold]{tier}[/bold] "
            f"([red]{strict:.0%}[/red] strict) — what would you change in the rule?",
            default="",
            show_default=False,
        ).strip()
        if note:
            entries.append((step, tier, strict, note))
    return entries


def _render_interim(ratings: list[Rating], threshold: float) -> None:
    """Compact running precision snapshot mid-session, so a partial
    trajectory appears before the final summary. One line per (step, tier)
    graded so far; high tier first to match grading order."""
    table = compute_precision(ratings)
    if not table:
        return
    graded = sum(v["total"] for v in table.values())
    console.print()
    console.rule(f"[dim]interim · {graded} graded so far[/dim]", style="dim")
    for (step, tier) in sorted(
        table.keys(), key=lambda k: (_TIER_PRIORITY.get(k[1], 99), k[0])
    ):
        v = table[(step, tier)]
        style = "red" if v["strict_precision"] < threshold else "green"
        console.print(
            f"  [dim]{step}[/dim] [bold]{tier}[/bold]  "
            f"n={v['total']}  "
            f"[{style}]{v['strict_precision']:.0%}[/{style}] strict"
        )


# ── Trajectory ───────────────────────────────────────────────────────────────


@dataclass
class CalibrationSession:
    """One persisted calibration session, parsed from calibration.jsonl."""

    session_id: str
    timestamp: str
    threshold: float
    precision: dict[tuple[str, str], dict]


def load_calibration_sessions(path: Path) -> list[CalibrationSession]:
    """Read calibration.jsonl into sessions sorted by timestamp; skip
    malformed lines. The on-disk precision_table is keyed "step|tier"
    (see persist_session); unpack it back to (step, tier) tuples.
    """
    sessions: list[CalibrationSession] = []
    if not path.exists():
        return sessions
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                _log.warning("calibration.jsonl: skipping malformed JSON line")
                continue
            precision: dict[tuple[str, str], dict] = {}
            for k, v in (d.get("precision_table") or {}).items():
                step, sep, tier = k.partition("|")
                if sep and isinstance(v, dict):
                    precision[(step, tier)] = v
            sessions.append(CalibrationSession(
                session_id=str(d.get("session_id", "")),
                timestamp=str(d.get("timestamp", "")),
                threshold=float(d.get("threshold", 0.0) or 0.0),
                precision=precision,
            ))
    sessions.sort(key=lambda s: s.timestamp)
    return sessions


def build_trajectories(
    sessions: list[CalibrationSession],
) -> dict[tuple[str, str], list[dict]]:
    """Per (step, tier): chronological strict-precision points, one per
    session that measured that group. Sessions must be timestamp-sorted.
    """
    traj: dict[tuple[str, str], list[dict]] = {}
    for s in sessions:
        for key, v in s.precision.items():
            traj.setdefault(key, []).append({
                "timestamp": s.timestamp,
                "strict": v.get("strict_precision", 0.0),
                "total": v.get("total", 0),
            })
    return traj


_SPARK_BLOCKS = "▁▂▃▄▅▆▇█"


def _sparkline(values: list[float]) -> str:
    """Render [0,1] values as a Unicode block sparkline."""
    chars = []
    for v in values:
        v = max(0.0, min(1.0, v))
        idx = min(len(_SPARK_BLOCKS) - 1, int(v * len(_SPARK_BLOCKS)))
        chars.append(_SPARK_BLOCKS[idx])
    return "".join(chars)


def _render_trajectory(
    traj: dict[tuple[str, str], list[dict]],
    n_sessions: int,
    threshold: float,
) -> None:
    """Per-(step, tier) strict-precision trajectory across sessions, high
    tier first. Latest value coloured against the most recent threshold."""
    table = Table(
        box=box.ROUNDED, show_header=True, header_style="bold cyan",
        title=f"[bold]Calibration trajectory[/bold]  "
              f"[dim]({n_sessions} session(s))[/dim]",
        title_justify="left",
    )
    table.add_column("Step",         no_wrap=True)
    table.add_column("Tier",         no_wrap=True, width=8)
    table.add_column("Sessions",     justify="right", width=8)
    table.add_column("Strict trend", no_wrap=True)
    table.add_column("First",        justify="right", width=6)
    table.add_column("Latest",       justify="right", width=7)
    table.add_column("Δ",            justify="right", width=7)

    for (step, tier) in sorted(
        traj.keys(), key=lambda k: (_TIER_PRIORITY.get(k[1], 99), k[0])
    ):
        points = traj[(step, tier)]
        strict_vals = [p["strict"] for p in points]
        first, latest = strict_vals[0], strict_vals[-1]
        latest_style = "green" if latest >= threshold else "red"
        if len(strict_vals) < 2:
            delta_str = "[dim]—[/dim]"
        else:
            delta = latest - first
            if delta > 0.0005:
                delta_str = f"[green]▲ {delta:+.0%}[/green]"
            elif delta < -0.0005:
                delta_str = f"[red]▼ {delta:+.0%}[/red]"
            else:
                delta_str = "[dim]→ 0%[/dim]"
        table.add_row(
            step, tier, str(len(points)),
            _sparkline(strict_vals),
            f"{first:.0%}",
            f"[{latest_style}]{latest:.0%}[/{latest_style}]",
            delta_str,
        )

    console.print()
    console.print(table)


def run_trajectory(calibration_path: Path) -> None:
    """Show per-tier strict-precision trends across calibration sessions."""
    sessions = load_calibration_sessions(calibration_path)
    if not sessions:
        console.print(Panel(
            f"No calibration history in [bold]{calibration_path}[/bold].\n"
            "Run [bold]audit-confidence[/bold] a few times first — each "
            "session appends one line this view trends over.",
            title="[yellow]No trajectory yet[/yellow]", border_style="yellow",
        ))
        return
    traj = build_trajectories(sessions)
    _render_trajectory(traj, len(sessions), sessions[-1].threshold)


# ── Entry point ──────────────────────────────────────────────────────────────


def run_audit_confidence(
    db: CalibreDB,
    audit_log_path: Path,
    output_path: Path,
    sample_size: int = 5,
    threshold: float = 0.7,
    steps_filter: list[str] | None = None,
    seed: int | None = None,
    interim_every: int = 5,
    revisions_path: Path | None = None,
) -> None:
    """Orchestrator: load, sample, prompt, summarise, persist."""
    rng = random.Random(seed) if seed is not None else random.Random()
    if revisions_path is None:
        revisions_path = output_path.parent / "rule-revisions.jsonl"
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
    graded = 0
    order = grading_order(sampled)
    for idx, (_key, rec) in enumerate(order, start=1):
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
            break
        ratings.append(Rating(record=rec, current_value=current, rating=label))
        if label != "skipped":
            graded += 1
            if interim_every and graded % interim_every == 0 and idx < total:
                _render_interim(ratings, threshold)

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

        if flagged:
            entries = _prompt_rule_revisions(flagged, precision_table)
            if entries:
                persist_rule_revisions(
                    revisions_path, session_id, threshold, entries,
                )
                console.print(
                    f"[dim]Captured {len(entries)} rule-revision note(s) to "
                    f"{revisions_path}.[/dim]"
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


# ── CLI handlers ──────────────────────────────────────────────────────────────

import os as _os
from typing import Optional, Annotated

from rich.text import Text

from ._common import app, console as _cli_console, DEFAULT_CONFIG_PATH, _load_config, _make_db


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
    cfg = _load_config(config)
    db = _make_db(cfg)

    if audit_log is not None:
        audit_log_path = audit_log
    else:
        env = _os.environ.get("CALIBRE_TOOLKIT_AUDIT_LOG")
        audit_log_path = Path(env).expanduser() if env else (
            Path.home() / ".calibre-toolkit" / "audit.log"
        )
    output_path = output or (Path.home() / ".calibre-toolkit" / "calibration.jsonl")

    steps_filter: Optional[list[str]] = None
    if step:
        steps_filter = [s.strip() for s in step.split(",") if s.strip()]

    _cli_console.print(
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
    calibration_path = calibration or (
        Path.home() / ".calibre-toolkit" / "calibration.jsonl"
    )
    run_trajectory(calibration_path)
