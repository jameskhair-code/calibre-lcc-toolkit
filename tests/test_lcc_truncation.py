"""Tests for v1.7 item 6: AI-only LCC truncation.

When the OL cascade returns no hit and the structured `lcc` field would
therefore be AI-only, truncate it to the class portion (letters + class
number, preserving any decimal subdivision) and drop the AI's unverified
Cutter and date. The AI's full reasoning still lives in `lcc_summary`.
Catalog-sourced suggestions are unchanged.
"""

from __future__ import annotations

import pytest

from calibre_toolkit.ai import LccSuggestion
from calibre_toolkit.modules.lcc import (
    _truncate_ai_only_lcc,
    _truncate_to_class_portion,
)


# ── _truncate_to_class_portion ──────────────────────────────────────────────


class TestTruncateToClassPortion:
    @pytest.mark.parametrize("inp,want", [
        # Author-Cutter forms: drop ".A77 D45 2008"
        ("PS3603.A77 D45 2008", "PS3603"),
        ("PR6059.S5 N48 2005", "PR6059"),
        ("BX4827.B57 A6 1965", "BX4827"),
        # Decimal class subdivision is preserved (e.g. PR9619.3)
        ("PR9619.3.K46 C66 1979", "PR9619.3"),
        # Whitespace-before-Cutter forms
        ("DK189 .W67 2003", "DK189"),
        ("PS3563 .O8749 N48", "PS3563"),
        # Already truncated — no-op
        ("PS3603", "PS3603"),
        ("PR9619.3", "PR9619.3"),
        # Case normalisation
        ("ps3603.a77", "PS3603"),
        # Single-letter class
        ("P3.B4", "P3"),
        # Three-letter class (DAW, KFD-style)
        ("DAW1051.W67", "DAW1051"),
        # Whitespace between letters and digits — collapsed
        ("PS 3603.A77", "PS3603"),
    ])
    def test_truncates(self, inp, want):
        assert _truncate_to_class_portion(inp) == want

    def test_empty_string(self):
        assert _truncate_to_class_portion("") == ""

    def test_unparseable_input_returned_verbatim(self):
        # Free-text the validator will flag separately — leave it for
        # the validation layer to handle, don't silently mangle.
        assert _truncate_to_class_portion("Fiction") == "Fiction"
        assert _truncate_to_class_portion("813.54") == "813.54"

    def test_letters_only_no_digit_class_returned_verbatim(self):
        # "KFD" alone has no class number — the truncator can't pick
        # a class portion, so it leaves the value alone for validation.
        assert _truncate_to_class_portion("KFD") == "KFD"

    def test_strips_leading_whitespace(self):
        assert _truncate_to_class_portion("  PS3603.A77") == "PS3603"


# ── _truncate_ai_only_lcc (in-place batch helper) ───────────────────────────


def _make_suggestion(
    book_id: int,
    lcc: str,
    *,
    source_authority: str = "ai_inference",
    lcc_summary: str = "AI summary prose",
    lcc_primary_class: str = "P - Language & Literature",
    lcc_secondary_class: str = "PS - American Literature",
) -> LccSuggestion:
    return LccSuggestion(
        book_id=book_id,
        title=f"Book {book_id}",
        authors=["Author Name"],
        current={k: "" for k in ("lcc", "lcc_primary_class", "lcc_secondary_class", "lcc_summary")},
        proposed={
            "lcc": lcc,
            "lcc_primary_class": lcc_primary_class,
            "lcc_secondary_class": lcc_secondary_class,
            "lcc_summary": lcc_summary,
        },
        confidence="medium",
        source_authority=source_authority,  # type: ignore[arg-type]
    )


class TestTruncateAiOnlyLcc:
    def test_truncates_ai_inference_suggestions(self):
        suggestions = [
            _make_suggestion(1, "PS3603.A77 D45 2008"),
            _make_suggestion(2, "PR6059.S5 N48 2005"),
        ]
        _truncate_ai_only_lcc(suggestions)
        assert suggestions[0].proposed["lcc"] == "PS3603"
        assert suggestions[1].proposed["lcc"] == "PR6059"

    def test_skips_open_library_suggestions(self):
        # Catalog-sourced — the Cutter/date came from OL member-library
        # cataloging, not the AI. Must NOT truncate.
        s = _make_suggestion(1, "PR9619.3.K46 C66 1979",
                             source_authority="open_library")
        _truncate_ai_only_lcc([s])
        assert s.proposed["lcc"] == "PR9619.3.K46 C66 1979"

    def test_skips_lc_catalog_suggestions(self):
        # Defensive — lc_catalog hits were removed in v1.3 but the
        # source_authority enum still includes the value. If one ever
        # reappears (e.g. a future LC restoration), it must not truncate.
        s = _make_suggestion(1, "PR9619.3.K46 C66 1979",
                             source_authority="lc_catalog")
        _truncate_ai_only_lcc([s])
        assert s.proposed["lcc"] == "PR9619.3.K46 C66 1979"

    def test_preserves_lcc_summary_verbatim(self):
        full_summary = (
            "A semi-autobiographical Booker Prize-winning novel "
            "following a young British boy's survival in Japanese-"
            "occupied Shanghai."
        )
        s = _make_suggestion(1, "PR6052.A46 E45 1984", lcc_summary=full_summary)
        _truncate_ai_only_lcc([s])
        assert s.proposed["lcc"] == "PR6052"
        assert s.proposed["lcc_summary"] == full_summary

    def test_preserves_primary_and_secondary_class_fields(self):
        s = _make_suggestion(
            1, "PS3603.A77 D45 2008",
            lcc_primary_class="P - Language & Literature",
            lcc_secondary_class="PS - American Literature",
        )
        _truncate_ai_only_lcc([s])
        # Truncation only touches the structured lcc field — primary
        # and secondary class strings are derived from class letters,
        # which the truncation preserves, so no need to touch them here.
        assert s.proposed["lcc_primary_class"] == "P - Language & Literature"
        assert s.proposed["lcc_secondary_class"] == "PS - American Literature"

    def test_already_truncated_unchanged(self):
        s = _make_suggestion(1, "PS3603")
        _truncate_ai_only_lcc([s])
        assert s.proposed["lcc"] == "PS3603"

    def test_empty_lcc_unchanged(self):
        s = _make_suggestion(1, "")
        _truncate_ai_only_lcc([s])
        assert s.proposed["lcc"] == ""

    def test_unparseable_lcc_unchanged(self):
        s = _make_suggestion(1, "Fiction")
        _truncate_ai_only_lcc([s])
        assert s.proposed["lcc"] == "Fiction"

    def test_mixed_batch_only_ai_only_entries_change(self):
        suggestions = [
            _make_suggestion(1, "PS3603.A77 D45 2008", source_authority="ai_inference"),
            _make_suggestion(2, "PR9619.3.K46 C66 1979", source_authority="open_library"),
            _make_suggestion(3, "PR6059.S5 N48 2005", source_authority="ai_inference"),
        ]
        _truncate_ai_only_lcc(suggestions)
        assert suggestions[0].proposed["lcc"] == "PS3603"
        assert suggestions[1].proposed["lcc"] == "PR9619.3.K46 C66 1979"
        assert suggestions[2].proposed["lcc"] == "PR6059"

    def test_in_place_no_new_objects(self):
        # The orchestrator passes the list directly; ensure we don't
        # accidentally replace the LccSuggestion objects.
        s = _make_suggestion(1, "PS3603.A77 D45 2008")
        identity = id(s)
        _truncate_ai_only_lcc([s])
        assert id(s) == identity
        # And the proposed dict identity is preserved too.
        proposed_id = id(s.proposed)
        _truncate_ai_only_lcc([s])
        assert id(s.proposed) == proposed_id

    def test_empty_list(self):
        # Must not raise — the AI batch might legitimately produce zero
        # suggestions if every book got a catalog hit.
        _truncate_ai_only_lcc([])
