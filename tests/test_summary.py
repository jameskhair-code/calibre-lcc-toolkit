"""Tests for the cross-pipeline summary panel (item 19)."""

from __future__ import annotations

from datetime import datetime
from io import StringIO

import pytest
from rich.console import Console
from rich.panel import Panel

from calibre_toolkit.summary import (
    StepSummary,
    render_summary_panel,
    _fmt_elapsed,
)
from calibre_toolkit.usage import TokenUsage, UsageAggregate


def _capture(panel: Panel, *, width: int = 100) -> str:
    buf = StringIO()
    Console(file=buf, width=width, force_terminal=False, no_color=True).print(panel)
    return buf.getvalue()


def _at(year: int = 2026, month: int = 5, day: int = 25) -> datetime:
    return datetime(year, month, day, 14, 30, 5)


# ── StepSummary defaults ──────────────────────────────────────────────────────


def test_step_summary_defaults_zero():
    s = StepSummary(step_label="x", started_at=_at(), elapsed_seconds=0.0)
    assert s.applied_high == 0
    assert s.applied_medium == 0
    assert s.applied_low == 0
    assert s.applied_total == 0
    assert s.skipped_already_done == 0
    assert s.skipped_declined == 0
    assert s.flagged_manual == 0
    assert s.pending_followup == 0
    assert s.extras == {}
    assert s.usage is None
    assert s.word_count is None


def test_step_summary_applied_total_sums_tiers():
    s = StepSummary(
        step_label="x",
        started_at=_at(),
        elapsed_seconds=1.0,
        applied_high=3,
        applied_medium=2,
        applied_low=1,
    )
    assert s.applied_total == 6


# ── _fmt_elapsed ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0.0, "0.0s"),
        (1.5, "1.5s"),
        (59.9, "59.9s"),
        (60.0, "1m 00s"),
        (90.0, "1m 30s"),
        (3599.0, "59m 59s"),
        (3600.0, "1h 00m 00s"),
        (7325.0, "2h 02m 05s"),
    ],
)
def test_fmt_elapsed_buckets(seconds: float, expected: str):
    assert _fmt_elapsed(seconds) == expected


# ── render_summary_panel ──────────────────────────────────────────────────────


def test_render_returns_panel_object():
    s = StepSummary(step_label="lcc-enrich", started_at=_at(), elapsed_seconds=5.0)
    panel = render_summary_panel(s)
    assert isinstance(panel, Panel)


def test_render_apply_mode_uses_applied_word():
    s = StepSummary(
        step_label="lcc-enrich",
        started_at=_at(),
        elapsed_seconds=5.0,
        applied_high=4,
    )
    out = _capture(render_summary_panel(s))
    assert "Applied" in out
    assert "Summary — lcc-enrich" in out
    assert "Proposed" not in out


def test_render_dry_run_mode_uses_proposed_word():
    s = StepSummary(
        step_label="lcc-enrich",
        started_at=_at(),
        elapsed_seconds=5.0,
        applied_high=4,
    )
    out = _capture(render_summary_panel(s, dry_run=True))
    assert "Proposed" in out
    assert "Dry-run summary — lcc-enrich" in out


def test_render_zero_applied_shows_none():
    s = StepSummary(step_label="lcc-enrich", started_at=_at(), elapsed_seconds=2.0)
    out = _capture(render_summary_panel(s))
    assert "none" in out


def test_render_tier_counts_visible():
    s = StepSummary(
        step_label="comments-enrich",
        started_at=_at(),
        elapsed_seconds=10.0,
        applied_high=7,
        applied_medium=3,
        applied_low=1,
    )
    out = _capture(render_summary_panel(s))
    assert "7 high" in out
    assert "3 medium" in out
    assert "1 low" in out


def test_render_only_populated_tiers_shown():
    s = StepSummary(
        step_label="comments-enrich",
        started_at=_at(),
        elapsed_seconds=10.0,
        applied_high=5,
    )
    out = _capture(render_summary_panel(s))
    assert "5 high" in out
    assert "medium" not in out
    assert " low" not in out


def test_render_skip_row_omitted_when_no_skips():
    s = StepSummary(
        step_label="x",
        started_at=_at(),
        elapsed_seconds=1.0,
        applied_high=2,
    )
    out = _capture(render_summary_panel(s))
    assert "Other outcomes" not in out


def test_render_skip_row_shown_when_any_skip():
    s = StepSummary(
        step_label="x",
        started_at=_at(),
        elapsed_seconds=1.0,
        applied_high=2,
        skipped_declined=3,
        flagged_manual=1,
    )
    out = _capture(render_summary_panel(s))
    assert "Other outcomes" in out
    assert "3 declined at review" in out
    assert "1 flagged for manual" in out


def test_render_already_done_shown():
    s = StepSummary(
        step_label="x",
        started_at=_at(),
        elapsed_seconds=1.0,
        skipped_already_done=42,
    )
    out = _capture(render_summary_panel(s))
    assert "42 already done" in out


def test_render_pending_followup_shown():
    s = StepSummary(
        step_label="enrich-identifiers",
        started_at=_at(),
        elapsed_seconds=1.0,
        pending_followup=5,
    )
    out = _capture(render_summary_panel(s))
    assert "5 pending follow-up" in out


def test_render_extras_by_lookup_method():
    s = StepSummary(
        step_label="enrich-identifiers",
        started_at=_at(),
        elapsed_seconds=1.0,
        extras={"by_lookup_method": {"isbn": 12, "title_author": 3}},
    )
    out = _capture(render_summary_panel(s))
    assert "By method" in out
    assert "isbn" in out
    assert "12" in out
    assert "title_author" in out


def test_render_extras_by_op():
    s = StepSummary(
        step_label="tags-cleanup",
        started_at=_at(),
        elapsed_seconds=1.0,
        extras={"by_op": {"merge": 3, "rename": 5, "drop": 2}},
    )
    out = _capture(render_summary_panel(s))
    assert "By operation" in out
    assert "merge" in out
    assert "rename" in out
    assert "drop" in out


def test_render_extras_unknown_category_falls_back_to_title_case():
    s = StepSummary(
        step_label="x",
        started_at=_at(),
        elapsed_seconds=1.0,
        extras={"by_planet": {"mars": 1}},
    )
    out = _capture(render_summary_panel(s), width=120)
    assert "By Planet" in out


def test_render_extras_sorted_by_count_descending():
    s = StepSummary(
        step_label="x",
        started_at=_at(),
        elapsed_seconds=1.0,
        extras={"by_op": {"low": 1, "high": 9, "mid": 5}},
    )
    out = _capture(render_summary_panel(s), width=120)
    idx_high = out.index("high")
    idx_mid = out.index("mid")
    idx_low = out.index("low")
    assert idx_high < idx_mid < idx_low


def test_render_word_count_only_shown_when_set():
    base = dict(step_label="comments-enrich", started_at=_at(), elapsed_seconds=1.0)
    out_without = _capture(render_summary_panel(StepSummary(**base)))
    out_with = _capture(render_summary_panel(StepSummary(**base, word_count=12345)))
    assert "Words written" not in out_without
    assert "Words written" in out_with
    assert "12,345" in out_with


def test_render_elapsed_formatted():
    s = StepSummary(step_label="x", started_at=_at(), elapsed_seconds=125.0)
    out = _capture(render_summary_panel(s))
    assert "2m 05s" in out


def test_render_started_timestamp_visible():
    s = StepSummary(step_label="x", started_at=_at(), elapsed_seconds=1.0)
    out = _capture(render_summary_panel(s))
    assert "2026-05-25 14:30:05" in out


def test_render_omits_usage_line_when_no_calls():
    s = StepSummary(
        step_label="x",
        started_at=_at(),
        elapsed_seconds=1.0,
        usage=UsageAggregate(),
    )
    out = _capture(render_summary_panel(s))
    assert "Tokens used" not in out


def test_render_includes_usage_line_when_calls_made():
    usage = UsageAggregate()
    usage.record(
        TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
        model="claude-sonnet-4-6",
    )
    s = StepSummary(
        step_label="lcc-enrich",
        started_at=_at(),
        elapsed_seconds=1.0,
        usage=usage,
    )
    out = _capture(render_summary_panel(s), width=140)
    assert "Tokens used" in out
    assert "lcc-enrich" in out
