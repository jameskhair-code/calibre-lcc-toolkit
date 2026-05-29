"""Author-change review gating (v1.8 PR 5).

From the 2026-05-28 clean-titles run: the AI dropped a real co-author at
medium confidence and it auto-applied under "all". These tests pin the
protection — author *removals* are detected (robust to spelling fixes) and
capped to low/review-only — while legitimate fixes still flow.
"""

from __future__ import annotations

import pytest

from calibre_toolkit.ai import CleanupSuggestion, _author_compare_key
from calibre_toolkit.modules.authors import _gate_author_removals


def _sugg(
    original: list[str],
    suggested: list[str],
    confidence: str = "medium",
) -> CleanupSuggestion:
    return CleanupSuggestion(
        book_id=1,
        original_title="T",
        original_authors=original,
        suggested_title="T",
        suggested_authors=suggested,
        confidence=confidence,
        title_changed=False,
        authors_changed=(original != suggested),
    )


# ── _author_compare_key ──────────────────────────────────────────────────────


def test_compare_key_is_case_diacritic_punct_order_insensitive():
    assert _author_compare_key("García Márquez, Gabriel") == \
           _author_compare_key("gabriel garcia marquez")
    assert _author_compare_key("Williams, Joy") == _author_compare_key("Joy Williams")


def test_compare_key_distinguishes_different_people():
    assert _author_compare_key("William Gaddis") != _author_compare_key("Joy Williams")


# ── removes_author ───────────────────────────────────────────────────────────


def test_removal_detected_when_coauthor_dropped():
    s = _sugg(["Joy Williams", "William Gaddis"], ["William Gaddis"])
    assert s.removes_author is True


def test_substitution_counts_as_removal():
    s = _sugg(["A Author", "B Author"], ["A Author", "C Author"])
    assert s.removes_author is True


def test_capitalisation_fix_is_not_removal():
    s = _sugg(["joy williams"], ["Joy Williams"])
    assert s.removes_author is False


def test_diacritic_fix_is_not_removal():
    # suggested side is the normalized (diacritic-stripped) form, as produced
    # by the cleanup pipeline; original carries the accent.
    s = _sugg(["Gabriel García Márquez"], ["Gabriel Garcia Marquez"])
    assert s.removes_author is False


def test_reorder_fix_is_not_removal():
    s = _sugg(["Williams, Joy"], ["Joy Williams"])
    assert s.removes_author is False


def test_adding_an_author_is_not_removal():
    s = _sugg(["A Author"], ["A Author", "B Author"])
    assert s.removes_author is False


def test_no_author_change_is_not_removal():
    s = _sugg(["A Author"], ["A Author"])
    assert s.removes_author is False


# ── _gate_author_removals ────────────────────────────────────────────────────


def test_gate_caps_removals_to_low_and_counts_them():
    removal = _sugg(["A Author", "B Author"], ["A Author"], confidence="medium")
    high_removal = _sugg(["X Author", "Y Author"], ["X Author"], confidence="high")
    legit = _sugg(["joy williams"], ["Joy Williams"], confidence="high")
    n = _gate_author_removals([removal, high_removal, legit])
    assert n == 2
    assert removal.confidence == "low"
    assert high_removal.confidence == "low"
    assert legit.confidence == "high"  # untouched


def test_gate_is_idempotent_and_skips_already_low():
    removal = _sugg(["A Author", "B Author"], ["A Author"], confidence="low")
    # Already low — counted as no change, so the operator notice isn't inflated.
    assert _gate_author_removals([removal]) == 0
    assert removal.confidence == "low"
