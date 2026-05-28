"""Tests for v1.7 item 7: catalog-source provenance in the summary panel.

`_build_source_breakdown_extras` packs OL direct / OL cascade / AI-only
counts into the `StepSummary.extras` shape under the `by_source`
category. The renderer in `summary.py` picks up the `by_source` label
from `_EXTRAS_LABELS` and prints one row per nonzero contribution.
"""

from __future__ import annotations

from datetime import datetime

from calibre_toolkit.modules.lcc import (
    _CatalogStats,
    _build_source_breakdown_extras,
)
from calibre_toolkit.summary import (
    _EXTRAS_LABELS,
    StepSummary,
    render_summary_panel,
)


# ── _build_source_breakdown_extras ──────────────────────────────────────────


class TestSourceBreakdownExtras:
    def test_mixed_run_returns_all_three_rows(self):
        stats = _CatalogStats(ol_direct_hits=10, ol_cascade_hits=7)
        # Simulate 13 AI-only suggestions (failures are silent).
        ai_suggestions = [object()] * 13
        out = _build_source_breakdown_extras(stats, ai_suggestions)
        assert out == {
            "by_source": {
                "OL direct": 10,
                "OL cascade": 7,
                "AI-only": 13,
            },
        }

    def test_zero_rows_dropped(self):
        # 100% OL-direct run — cascade and AI rows should not appear.
        stats = _CatalogStats(ol_direct_hits=30, ol_cascade_hits=0)
        out = _build_source_breakdown_extras(stats, [])
        assert out == {"by_source": {"OL direct": 30}}
        assert "OL cascade" not in out["by_source"]
        assert "AI-only" not in out["by_source"]

    def test_only_cascade(self):
        stats = _CatalogStats(ol_direct_hits=0, ol_cascade_hits=15)
        out = _build_source_breakdown_extras(stats, [])
        assert out == {"by_source": {"OL cascade": 15}}

    def test_only_ai(self):
        # No catalog hits — pure AI fallback run.
        stats = _CatalogStats(ol_direct_hits=0, ol_cascade_hits=0)
        out = _build_source_breakdown_extras(stats, [object()] * 30)
        assert out == {"by_source": {"AI-only": 30}}

    def test_nothing_produced_returns_empty_dict(self):
        # Empty search, nothing to do — extras should be empty so the
        # panel doesn't render a source row at all.
        stats = _CatalogStats()
        out = _build_source_breakdown_extras(stats, [])
        assert out == {}

    def test_ai_only_count_tracks_suggestions_not_books(self):
        # AI failed on some books — those don't get counted, mirroring
        # how the rest of the panel only reports what was produced.
        stats = _CatalogStats(ol_direct_hits=0, ol_cascade_hits=0)
        # 30 books went to AI, but only 25 produced suggestions.
        ai_suggestions = [object()] * 25
        out = _build_source_breakdown_extras(stats, ai_suggestions)
        assert out["by_source"]["AI-only"] == 25


# ── Renderer wiring (summary.py) ────────────────────────────────────────────


class TestPanelRendersSourceRow:
    def test_by_source_label_registered(self):
        # Without a registered label, the renderer would fall back to
        # title-casing the category key ("By Source", with an extra
        # capital S). Verify the explicit label is in place.
        assert _EXTRAS_LABELS["by_source"] == "By source"

    def test_render_does_not_crash_with_by_source_extras(self):
        # Smoke test the renderer end-to-end with the new extras
        # category present — catches any regression in the panel's
        # extras-rendering loop when the new label is exercised.
        summary = StepSummary(
            step_label="lcc-enrich",
            started_at=datetime(2026, 5, 27, 21, 0, 0),
            elapsed_seconds=12.34,
            applied_high=5,
            applied_medium=10,
            applied_low=2,
            extras={"by_source": {"OL direct": 10, "OL cascade": 7, "AI-only": 13}},
        )
        panel = render_summary_panel(summary, dry_run=True)
        # Just confirm we got a Panel back; deeper rendering checks
        # would couple too tightly to Rich's internal layout.
        from rich.panel import Panel
        assert isinstance(panel, Panel)
