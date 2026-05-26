"""Tests for the TUI pipeline overview row renderer (item 22)."""

from __future__ import annotations

import pytest

from calibre_toolkit.tui.app import _render_overview_row


def _strip_markup(s: str) -> str:
    """Strip Rich markup tags so assertions can target the visible glyphs."""
    import re
    return re.sub(r"\[/?[^\]]*\]", "", s)


# ── State detection ──────────────────────────────────────────────────────────


def test_not_started_zero_done_nonzero_total():
    row = _render_overview_row("Title & Author", "01", done=0, total=100)
    plain = _strip_markup(row)
    assert "○" in plain
    assert "not-started" in plain
    assert "0%" in plain


def test_in_progress_partial():
    row = _render_overview_row("Identifiers", "02", done=40, total=100)
    plain = _strip_markup(row)
    assert "◐" in plain
    assert "in-progress" in plain
    assert "40%" in plain


def test_done_full():
    row = _render_overview_row("LCC", "03", done=100, total=100)
    plain = _strip_markup(row)
    assert "●" in plain
    assert "done" in plain
    assert "100%" in plain


def test_done_overshoots_total():
    """If something writes more than total (edge case), still 'done'."""
    row = _render_overview_row("LCC", "03", done=120, total=100)
    plain = _strip_markup(row)
    assert "●" in plain
    assert "done" in plain


def test_zero_total_treated_as_not_started():
    row = _render_overview_row("Empty step", "01", done=0, total=0)
    plain = _strip_markup(row)
    assert "○" in plain
    assert "not-started" in plain
    assert "0%" in plain


# ── Visual structure ─────────────────────────────────────────────────────────


def test_row_contains_step_number():
    row = _render_overview_row("LCC", "03", done=50, total=100)
    plain = _strip_markup(row)
    assert "03" in plain


def test_row_contains_step_name():
    row = _render_overview_row("Comments", "04", done=10, total=20)
    plain = _strip_markup(row)
    assert "Comments" in plain


def test_row_contains_bar_glyphs():
    row = _render_overview_row("LCC", "03", done=50, total=100)
    plain = _strip_markup(row)
    assert "█" in plain
    assert "░" in plain


def test_long_step_name_truncated_to_22_chars():
    # Names beyond 22 chars get truncated by the fixed-width formatter so
    # the bar column stays aligned across all five rows.
    long_name = "A" * 50
    row = _render_overview_row(long_name, "01", done=0, total=100)
    plain = _strip_markup(row)
    # 22 As should appear; not 50.
    assert "A" * 22 in plain
    assert "A" * 23 not in plain


def test_empty_number_renders_as_padding():
    row = _render_overview_row("Unnumbered", "", done=10, total=20)
    plain = _strip_markup(row)
    assert "Unnumbered" in plain
    # No number, but bar/percentage/label still present
    assert "50%" in plain
    assert "in-progress" in plain


# ── Bar fill correctness ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "done,total,expected_filled",
    [
        (0, 100, 0),
        (25, 100, 5),
        (50, 100, 10),
        (75, 100, 15),
        (100, 100, 20),
        (33, 100, 6),
    ],
)
def test_bar_fill_matches_percentage(done: int, total: int, expected_filled: int):
    row = _render_overview_row("X", "01", done=done, total=total)
    plain = _strip_markup(row)
    filled_count = plain.count("█")
    assert filled_count == expected_filled
    empty_count = plain.count("░")
    assert filled_count + empty_count == 20  # bar width
