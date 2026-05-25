"""Tests for the v1.2 item 8 honest-source-attribution layer.

Two layers under test:

1. `_normalise_lcc_source_authority` enforces the SRC-06 contract: any
   `lc_catalog` / `worldcat_consensus` claim from the AI is downgraded
   to `ai_inference` with a visible note appended, since the AI is only
   called for books that already missed the direct catalog lookup.

2. `LccSuggestion.attribution_prefix` is the trustworthy display prefix —
   it derives purely from `source_authority`, never from the AI's free-
   text source string.

3. `_build_catalog_suggestion` populates `source_authority` correctly for
   LC catalog vs Open Library hits.
"""

from __future__ import annotations

import json

import pytest

from calibre_toolkit.ai import (
    LccSuggestion,
    _normalise_lcc_source_authority,
    _parse_lcc_response,
)
from calibre_toolkit.db import Book
from calibre_toolkit.modules.lcc import _build_catalog_suggestion
from calibre_toolkit.services.lc_catalog import CatalogHit


# ── _normalise_lcc_source_authority ────────────────────────────────────────


class TestNormaliseSourceAuthority:
    def test_unknown_value_defaults_to_ai_inference(self):
        authority, notes = _normalise_lcc_source_authority("nonsense", "")
        assert authority == "ai_inference"
        assert notes == ""

    def test_empty_value_defaults_to_ai_inference(self):
        authority, notes = _normalise_lcc_source_authority(None, "")
        assert authority == "ai_inference"

    def test_lc_catalog_claim_downgraded(self):
        authority, notes = _normalise_lcc_source_authority("lc_catalog", "")
        assert authority == "ai_inference"
        assert "downgraded" in notes
        assert "lc_catalog" in notes

    def test_worldcat_claim_downgraded(self):
        authority, notes = _normalise_lcc_source_authority(
            "worldcat_consensus", "Original note.",
        )
        assert authority == "ai_inference"
        assert "Original note." in notes
        assert "worldcat_consensus" in notes

    def test_open_library_passes_through(self):
        authority, notes = _normalise_lcc_source_authority("open_library", "x")
        assert authority == "open_library"
        assert notes == "x"

    def test_ai_inference_passes_through(self):
        authority, notes = _normalise_lcc_source_authority("ai_inference", "x")
        assert authority == "ai_inference"
        assert notes == "x"

    def test_case_insensitive(self):
        authority, _ = _normalise_lcc_source_authority("AI_INFERENCE", "")
        assert authority == "ai_inference"


# ── attribution_prefix ─────────────────────────────────────────────────────


class TestAttributionPrefix:
    @pytest.mark.parametrize("authority,expected", [
        ("lc_catalog",         "[LC]"),
        ("worldcat_consensus", "[WC]"),
        ("open_library",       "[OL]"),
        ("ai_inference",       "[AI]"),
    ])
    def test_known_values(self, authority, expected):
        s = LccSuggestion(
            book_id=1, title="t", authors=["a"],
            current={}, proposed={}, confidence="high",
            source_authority=authority,
        )
        assert s.attribution_prefix == expected

    def test_unknown_authority_falls_back_to_ai_prefix(self):
        s = LccSuggestion(
            book_id=1, title="t", authors=["a"],
            current={}, proposed={}, confidence="high",
        )
        # Bypass dataclass type check — simulate a future value we don't recognise.
        object.__setattr__(s, "source_authority", "future_value")
        assert s.attribution_prefix == "[AI]"

    def test_prose_source_cannot_influence_prefix(self):
        """The whole point of v1.2 item 8: prose claims do not move the prefix."""
        s = LccSuggestion(
            book_id=1, title="t", authors=["a"],
            current={}, proposed={}, confidence="high",
            source="Library of Congress catalog, exact ISBN match",
            source_authority="ai_inference",
        )
        assert s.attribution_prefix == "[AI]"


# ── _parse_lcc_response wires source_authority through ────────────────────


def _book(bid: int = 1) -> Book:
    return Book(id=bid, title="Title", authors=["A"])


class TestParseLccResponse:
    def test_default_authority_when_ai_overclaims(self):
        raw = json.dumps([{
            "id": 1, "lcc": "PR6059", "lcc_primary_class": "P",
            "lcc_secondary_class": "PR", "lcc_summary": "summary",
            "confidence": "high",
            "source_authority": "lc_catalog",
            "source": "Library of Congress catalog (ISBN ...)",
            "notes": "original ai note",
        }])
        suggestions = _parse_lcc_response(raw, [_book(1)], {1: {}})
        assert len(suggestions) == 1
        assert suggestions[0].source_authority == "ai_inference"
        assert "original ai note" in suggestions[0].notes
        assert "downgraded" in suggestions[0].notes

    def test_ai_inference_claim_preserved(self):
        raw = json.dumps([{
            "id": 1, "lcc": "PR", "confidence": "low",
            "source_authority": "ai_inference",
            "notes": "schedule-derived",
        }])
        suggestions = _parse_lcc_response(raw, [_book(1)], {1: {}})
        assert suggestions[0].source_authority == "ai_inference"
        assert suggestions[0].notes == "schedule-derived"

    def test_missing_field_defaults_to_ai_inference(self):
        raw = json.dumps([{"id": 1, "lcc": "PR", "confidence": "low"}])
        suggestions = _parse_lcc_response(raw, [_book(1)], {1: {}})
        assert suggestions[0].source_authority == "ai_inference"


# ── _build_catalog_suggestion ──────────────────────────────────────────────


class TestBuildCatalogSuggestion:
    """After the v1.3 LC removal every catalog hit is Open Library
    (direct or via the edition cascade). There is no longer a code
    path that produces an LC-attributed CatalogHit, so the only
    behaviour to lock in is the OL one."""

    def test_open_library_direct_hit_marks_open_library_medium(self):
        hit = CatalogHit(call_number="PR6059.S5 N48 2005",
                         source="Open Library (ISBN 9780571258246)")
        book = _book(42)
        s = _build_catalog_suggestion(book, {}, hit)
        assert s.source_authority == "open_library"
        assert s.attribution_prefix == "[OL]"
        assert s.confidence == "medium"

    def test_edition_cascade_hit_also_marks_open_library(self):
        hit = CatalogHit(
            call_number="PR9619.3.K46 C66",
            source="Open Library via edition cascade (seed ISBN x, matched sibling y)",
        )
        book = _book(42)
        s = _build_catalog_suggestion(book, {}, hit)
        assert s.source_authority == "open_library"
        assert s.confidence == "medium"
