"""
Structured end-of-run summary panel shared across step modules.

Replaces the per-module ``[bold green]Done![/bold green] X applied, Y …`` line
with a single dataclass shape that every batch enrichment step builds and a
Rich render helper that formats it identically across the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from .usage import UsageAggregate, format_summary


@dataclass
class StepSummary:
    """Cross-pipeline shape for end-of-run reporting.

    Counters default to zero so each step populates only the fields its flow
    produces. Step-specific breakdowns live in ``extras`` keyed by category
    (e.g. ``{"by_lookup_method": {"isbn": 12, "title_author": 3}}``).
    """

    step_label: str
    started_at: datetime
    elapsed_seconds: float

    applied_high: int = 0
    applied_medium: int = 0
    applied_low: int = 0

    skipped_already_done: int = 0
    skipped_declined: int = 0
    flagged_manual: int = 0
    pending_followup: int = 0

    extras: dict[str, dict[str, int]] = field(default_factory=dict)

    usage: Optional[UsageAggregate] = None
    word_count: Optional[int] = None

    @property
    def applied_total(self) -> int:
        return self.applied_high + self.applied_medium + self.applied_low


# ── Render helpers ────────────────────────────────────────────────────────────


def _fmt_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m {secs:02d}s"


def _kv_row(table: Table, label: str, value: Text | str) -> None:
    if isinstance(value, str):
        value = Text(value)
    table.add_row(Text(label, style="dim"), value)


def _tier_text(s: StepSummary) -> Text:
    if not (s.applied_high or s.applied_medium or s.applied_low):
        return Text("none", style="dim")
    parts: list[tuple[str, str]] = []
    if s.applied_high:
        parts.append((f"{s.applied_high} high", "green"))
    if s.applied_medium:
        parts.append((f"{s.applied_medium} medium", "yellow"))
    if s.applied_low:
        parts.append((f"{s.applied_low} low", "red"))
    out = Text()
    for i, (txt, style) in enumerate(parts):
        if i:
            out.append("  ·  ", style="dim")
        out.append(txt, style=style)
    return out


def _skip_text(s: StepSummary) -> Optional[Text]:
    bits: list[tuple[str, str]] = []
    if s.skipped_already_done:
        bits.append((f"{s.skipped_already_done} already done", "dim"))
    if s.skipped_declined:
        bits.append((f"{s.skipped_declined} declined at review", "yellow"))
    if s.flagged_manual:
        bits.append((f"{s.flagged_manual} flagged for manual", "yellow"))
    if s.pending_followup:
        bits.append((f"{s.pending_followup} pending follow-up", "dim"))
    if not bits:
        return None
    out = Text()
    for i, (txt, style) in enumerate(bits):
        if i:
            out.append("  ·  ", style="dim")
        out.append(txt, style=style)
    return out


def _extras_text(category: str, counts: dict[str, int]) -> Text:
    if not counts:
        return Text("none", style="dim")
    out = Text()
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    for i, (name, n) in enumerate(items):
        if i:
            out.append("  ·  ", style="dim")
        out.append(f"{name}: ", style="dim")
        out.append(str(n), style="bold")
    return out


_EXTRAS_LABELS = {
    "by_lookup_method": "By method",
    "by_op": "By operation",
    "by_tag_category": "By category",
}


def render_summary_panel(
    summary: StepSummary,
    *,
    dry_run: bool = False,
) -> Panel:
    """Build the Rich Panel printed at end-of-run.

    Dry-run mode swaps the applied/marked-complete framing for a
    "proposed" framing; the rest of the layout is identical.
    """
    table = Table.grid(padding=(0, 1), expand=False)
    table.add_column(style="dim", no_wrap=True)
    table.add_column()

    title_word = "Proposed" if dry_run else "Applied"
    _kv_row(table, f"{title_word} (by tier):", _tier_text(summary))

    skip_text = _skip_text(summary)
    if skip_text is not None:
        _kv_row(table, "Other outcomes:", skip_text)

    for category, counts in summary.extras.items():
        label = _EXTRAS_LABELS.get(category, category.replace("_", " ").title())
        _kv_row(table, f"{label}:", _extras_text(category, counts))

    if summary.word_count is not None:
        _kv_row(table, "Words written:", f"{summary.word_count:,}")

    timestamp_str = summary.started_at.strftime("%Y-%m-%d %H:%M:%S")
    _kv_row(
        table,
        "Run:",
        f"started {timestamp_str}  ·  elapsed {_fmt_elapsed(summary.elapsed_seconds)}",
    )

    body: list = [table]

    if summary.usage is not None and summary.usage.call_count > 0:
        body.append(Text(""))
        body.append(Text.from_markup(
            f"[dim]{format_summary(summary.usage, step_label=summary.step_label)}[/dim]"
        ))

    title_prefix = "Dry-run summary" if dry_run else "Summary"
    return Panel(
        Group(*body),
        title=f"[bold green]{title_prefix} — {summary.step_label}[/bold green]",
        title_align="left",
        border_style="green" if not dry_run else "cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )
