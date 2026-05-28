"""audit-log — make the persistent audit trail queryable (roadmap item 18).

The audit log (`~/.calibre-toolkit/audit.log`, JSONL since v1.1 — one line per
metadata write) was grep-only. This command reads it back with simple filters
and renders a compact table. Purely read-only: it opens one file and writes
nothing.

The low-level reader (`read_audit_entries`) and the filter (`filter_entries`)
are the canonical audit-log access path. `commands/audit.py`'s calibration
loader builds on them rather than re-opening the file, and the re-grade
workflow reuses them too — there must be exactly one parser.

Unlike calibration's `load_audit_records`, the reader here returns *every*
well-formed line — AI writes and manual marker writes alike. Filtering is the
caller's job.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from ..logging_config import get_logger

_log = get_logger(__name__)
console = Console()


# ── Reader (shared) ──────────────────────────────────────────────────────────


def read_audit_entries(path: Path) -> list[dict]:
    """Parse the JSONL audit log into raw dict records; skip malformed lines.

    The canonical low-level reader. Returns entries in file order (oldest
    first, since the log is append-only). Non-object JSON lines are skipped —
    every record the writer emits is an object.
    """
    entries: list[dict] = []
    if not path.exists():
        return entries
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
            if isinstance(d, dict):
                entries.append(d)
    return entries


def _parse_ts(value: object) -> datetime | None:
    """Parse an ISO-8601 audit timestamp; None if absent/unparseable.

    Naive timestamps (pre-tz writes, if any) are assumed UTC so they compare
    cleanly against the timezone-aware `--since` cutoff.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def filter_entries(
    entries: list[dict],
    *,
    field: str | None = None,
    book_id: int | None = None,
    step: str | None = None,
    since: datetime | None = None,
) -> list[dict]:
    """Return entries matching every supplied filter (AND semantics).

    A None filter is inactive. `since` keeps entries timestamped on or after
    the cutoff; entries with a missing or unparseable timestamp are dropped
    when `since` is active (they cannot be shown to satisfy the bound).
    """
    out: list[dict] = []
    for d in entries:
        if field is not None and d.get("field") != field:
            continue
        if book_id is not None:
            try:
                if int(d.get("book_id")) != book_id:
                    continue
            except (TypeError, ValueError):
                continue
        if step is not None and d.get("step") != step:
            continue
        if since is not None:
            ts = _parse_ts(d.get("timestamp"))
            if ts is None or ts < since:
                continue
        out.append(d)
    return out


def parse_since(value: str) -> datetime:
    """Parse a `--since` value (date `YYYY-MM-DD` or full ISO timestamp).

    A date-only value is anchored at midnight UTC; a naive timestamp is
    assumed UTC. Raises typer.BadParameter on anything unparseable.
    """
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise typer.BadParameter(
            f"'{value}' is not an ISO date or timestamp "
            "(expected e.g. 2026-05-28 or 2026-05-28T14:00:00)"
        )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ── Display ──────────────────────────────────────────────────────────────────


def _preview(value: object, max_chars: int = 80) -> str:
    """Single-line, HTML-stripped preview of an audit value."""
    if value is None:
        return "(no value)"
    if isinstance(value, list):
        s = ", ".join(str(x) for x in value)
    else:
        s = re.sub(r"<[^>]+>", " ", str(value))
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= max_chars else s[:max_chars].rstrip() + "…"


def _short_ts(value: object) -> str:
    """`YYYY-MM-DD HH:MM` for table display; raw string if unparseable."""
    dt = _parse_ts(value)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else str(value or "")


def run_audit_log_show(
    path: Path,
    *,
    field: str | None = None,
    book_id: int | None = None,
    step: str | None = None,
    since: datetime | None = None,
    limit: int = 50,
) -> None:
    """Read, filter, and render the audit log as a compact table.

    Shows the most recent `limit` matches (0 = all). Entries render oldest to
    newest so the latest write is at the bottom, matching how the log reads.
    """
    entries = read_audit_entries(path)
    if not entries:
        console.print(Panel(
            f"No audit entries in [bold]{path}[/bold].\n"
            "The log fills as the toolkit applies metadata writes.",
            title="[yellow]Empty audit log[/yellow]", border_style="yellow",
        ))
        return

    matched = filter_entries(
        entries, field=field, book_id=book_id, step=step, since=since,
    )
    if not matched:
        console.print(Panel(
            "No audit entries match the given filters.",
            title="[yellow]No matches[/yellow]", border_style="yellow",
        ))
        return

    shown = matched[-limit:] if limit and limit > 0 else matched

    table = Table(
        box=box.ROUNDED, show_header=True, header_style="bold cyan",
        title=f"[bold]Audit log[/bold]  "
              f"[dim](showing {len(shown)} of {len(matched)} matched)[/dim]",
        title_justify="left",
    )
    table.add_column("When",  no_wrap=True)
    table.add_column("Book",  justify="right", no_wrap=True)
    table.add_column("Step",  no_wrap=True)
    table.add_column("Field", no_wrap=True)
    table.add_column("Tier",  no_wrap=True)
    table.add_column("Value")

    for d in shown:
        table.add_row(
            _short_ts(d.get("timestamp")),
            str(d.get("book_id", "")),
            str(d.get("step", "")),
            str(d.get("field", "")),
            str(d.get("confidence", "")),
            _preview(d.get("new_value")),
        )

    console.print()
    console.print(table)
