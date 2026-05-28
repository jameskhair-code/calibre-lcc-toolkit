"""Tests for v1.7 item 5: combine OL hits with description-grounded summaries.

When a book has both an OL catalog hit AND a prefetched description,
one extra small AI call replaces the catalog-template `lcc_summary`
with description-grounded prose. The catalog-derived
`lcc` / `lcc_primary_class` / `lcc_secondary_class` fields are
unchanged. Catalog hits without descriptions keep the template summary.
"""

from __future__ import annotations

import json

import pytest

from calibre_toolkit.ai import (
    AIClient,
    LccSuggestion,
    _build_lcc_summary_user_message,
)
from calibre_toolkit.db import Book
from calibre_toolkit.modules.lcc import _apply_ai_summary_to_catalog_hits
from calibre_toolkit.schemas import (
    LccSummaryItem,
    SchemaViolation,
    validate_lcc_summary,
)
from calibre_toolkit.services.book_description import BookDescription


# ── Schema / validator ──────────────────────────────────────────────────────


class TestValidateLccSummary:
    def test_parses_valid_response(self):
        raw = json.dumps([
            {"id": 1, "lcc_summary": "A semi-autobiographical novel of internment in wartime Shanghai."},
            {"id": 2, "lcc_summary": "How the Romanov dynasty used court ceremony to project imperial authority."},
        ])
        rows = validate_lcc_summary(raw)
        assert len(rows) == 2
        assert rows[0].id == 1
        assert rows[1].lcc_summary.startswith("How the Romanov")

    def test_missing_summary_defaults_to_empty(self):
        # Identity mismatch signal — empty string is valid (caller keeps template).
        raw = json.dumps([{"id": 1, "lcc_summary": ""}])
        rows = validate_lcc_summary(raw)
        assert rows[0].lcc_summary == ""

    def test_extra_fields_ignored(self):
        raw = json.dumps([{"id": 1, "lcc_summary": "prose", "confidence": "high"}])
        rows = validate_lcc_summary(raw)
        assert rows[0].id == 1
        assert rows[0].lcc_summary == "prose"

    def test_invalid_json_raises(self):
        with pytest.raises(SchemaViolation):
            validate_lcc_summary("not valid")

    def test_missing_id_raises(self):
        raw = json.dumps([{"lcc_summary": "prose"}])
        with pytest.raises(SchemaViolation):
            validate_lcc_summary(raw)


# ── User-message construction ───────────────────────────────────────────────


class TestBuildSummaryUserMessage:
    def test_includes_catalog_context_and_description(self):
        books = [Book(id=1, title="Empire of the Sun", authors=["J. G. Ballard"])]
        catalog_ctx = {
            1: {
                "lcc": "PR6052.A46 E45 1984",
                "lcc_primary_class": "P - Language & Literature",
                "lcc_secondary_class": "PR - English Literature",
                "catalog_source": "Open Library (ISBN 9780571258246)",
            },
        }
        description_map = {
            1: BookDescription(
                text="A semi-autobiographical novel set in Japanese-occupied Shanghai.",
                source="Open Library",
                categories=["Fiction"],
            ),
        }
        msg = _build_lcc_summary_user_message(books, catalog_ctx, description_map)
        payload = json.loads(msg)
        assert len(payload) == 1
        item = payload[0]
        assert item["id"] == 1
        assert item["lcc"] == "PR6052.A46 E45 1984"
        assert item["lcc_primary_class"] == "P - Language & Literature"
        assert item["lcc_secondary_class"] == "PR - English Literature"
        assert item["catalog_source"] == "Open Library (ISBN 9780571258246)"
        assert "Japanese-occupied" in item["description"]
        assert item["description_source"] == "Open Library"
        assert item["description_categories"] == ["Fiction"]

    def test_omits_description_fields_when_absent(self):
        books = [Book(id=1, title="X", authors=["Y"])]
        catalog_ctx = {1: {"lcc": "PR6052", "lcc_primary_class": "P", "lcc_secondary_class": "PR", "catalog_source": "OL"}}
        msg = _build_lcc_summary_user_message(books, catalog_ctx, {})
        item = json.loads(msg)[0]
        assert "description" not in item
        assert "description_source" not in item

    def test_omits_description_fields_when_text_empty(self):
        books = [Book(id=1, title="X", authors=["Y"])]
        catalog_ctx = {1: {"lcc": "PR6052", "lcc_primary_class": "P", "lcc_secondary_class": "PR", "catalog_source": "OL"}}
        description_map = {1: BookDescription(text="", source="Open Library", categories=[])}
        msg = _build_lcc_summary_user_message(books, catalog_ctx, description_map)
        item = json.loads(msg)[0]
        assert "description" not in item


# ── AIClient.suggest_lcc_summary ────────────────────────────────────────────


class TestSuggestLccSummary:
    def _client(self):
        # Real AIClient with no API key — we patch the network layer below.
        return AIClient(api_key="test", model="claude-sonnet-4-6", step_label="lcc-enrich")

    def test_returns_dict_of_id_to_prose(self, monkeypatch):
        client = self._client()
        response_body = json.dumps([
            {"id": 1, "lcc_summary": "Prose for book 1."},
            {"id": 2, "lcc_summary": "Prose for book 2."},
        ])
        monkeypatch.setattr(AIClient, "_call",
                            lambda self, u, s, max_tokens=8192: response_body)
        books = [Book(id=1, title="A", authors=["X"]),
                 Book(id=2, title="B", authors=["Y"])]
        ctx = {1: {"lcc": "PR1", "lcc_primary_class": "P", "lcc_secondary_class": "PR", "catalog_source": "OL"},
               2: {"lcc": "PR2", "lcc_primary_class": "P", "lcc_secondary_class": "PR", "catalog_source": "OL"}}
        descs = {
            1: BookDescription(text="desc 1", source="OL", categories=[]),
            2: BookDescription(text="desc 2", source="OL", categories=[]),
        }
        out = client.suggest_lcc_summary(books, ctx, descs)
        assert out == {1: "Prose for book 1.", 2: "Prose for book 2."}

    def test_empty_input_returns_empty_dict(self, monkeypatch):
        client = self._client()
        def explode(*args, **kwargs):
            raise AssertionError("HTTP must not be called for empty input")
        monkeypatch.setattr(AIClient, "_call", explode)
        assert client.suggest_lcc_summary([], {}, {}) == {}

    def test_omits_books_with_empty_ai_summary(self, monkeypatch):
        client = self._client()
        # AI signals identity mismatch for book 2 by returning empty string.
        response_body = json.dumps([
            {"id": 1, "lcc_summary": "Real prose for 1."},
            {"id": 2, "lcc_summary": ""},
        ])
        monkeypatch.setattr(AIClient, "_call",
                            lambda self, u, s, max_tokens=8192: response_body)
        books = [Book(id=1, title="A", authors=["X"]),
                 Book(id=2, title="B", authors=["Y"])]
        ctx = {bid: {"lcc": "X", "lcc_primary_class": "P", "lcc_secondary_class": "PR", "catalog_source": "OL"}
               for bid in (1, 2)}
        descs = {bid: BookDescription(text=f"d{bid}", source="OL", categories=[]) for bid in (1, 2)}
        out = client.suggest_lcc_summary(books, ctx, descs)
        assert out == {1: "Real prose for 1."}
        assert 2 not in out


# ── _apply_ai_summary_to_catalog_hits (integration) ─────────────────────────


def _catalog_suggestion(
    book_id: int,
    *,
    lcc: str = "PR6052.A46 E45 1984",
    primary: str = "P - Language & Literature",
    secondary: str = "PR - English Literature",
    summary: str = "Classified by Open Library under PR — English Literature.",
    source: str = "Open Library (ISBN 9780571258246)",
) -> LccSuggestion:
    return LccSuggestion(
        book_id=book_id,
        title=f"Book {book_id}",
        authors=["Author"],
        current={k: "" for k in ("lcc", "lcc_primary_class", "lcc_secondary_class", "lcc_summary")},
        proposed={
            "lcc": lcc,
            "lcc_primary_class": primary,
            "lcc_secondary_class": secondary,
            "lcc_summary": summary,
        },
        confidence="medium",
        source=source,
        source_authority="open_library",
    )


class _StubAI:
    """Captures suggest_lcc_summary calls and returns a configurable result."""

    def __init__(self, result=None, raise_exc=None):
        self.result = result if result is not None else {}
        self.raise_exc = raise_exc
        self.call_count = 0
        self.last_books: list = []
        self.last_context: dict = {}
        self.last_descriptions: dict = {}

    def suggest_lcc_summary(self, books, catalog_context_map, description_map, batch_size=10):
        self.call_count += 1
        self.last_books = books
        self.last_context = catalog_context_map
        self.last_descriptions = description_map
        if self.raise_exc:
            raise self.raise_exc
        return dict(self.result)


class TestApplyAiSummaryToCatalogHits:
    def test_replaces_template_summary_with_ai_prose(self):
        books = [Book(id=1, title="Empire of the Sun", authors=["J. G. Ballard"])]
        sug = _catalog_suggestion(1)
        original_template = sug.proposed["lcc_summary"]
        ai_prose = "A semi-autobiographical novel of internment in wartime Shanghai."
        descs = {1: BookDescription(text="d", source="OL", categories=[])}
        ai = _StubAI(result={1: ai_prose})

        _apply_ai_summary_to_catalog_hits(ai, books, [sug], descs, batch_size=10)

        assert ai.call_count == 1
        assert sug.proposed["lcc_summary"] == ai_prose
        assert sug.proposed["lcc_summary"] != original_template

    def test_preserves_catalog_class_fields(self):
        books = [Book(id=1, title="X", authors=["Y"])]
        sug = _catalog_suggestion(
            1,
            lcc="PR6052.A46 E45 1984",
            primary="P - Language & Literature",
            secondary="PR - English Literature",
        )
        descs = {1: BookDescription(text="d", source="OL", categories=[])}
        ai = _StubAI(result={1: "AI prose"})

        _apply_ai_summary_to_catalog_hits(ai, books, [sug], descs, batch_size=10)

        # Catalog-derived class fields are untouched.
        assert sug.proposed["lcc"] == "PR6052.A46 E45 1984"
        assert sug.proposed["lcc_primary_class"] == "P - Language & Literature"
        assert sug.proposed["lcc_secondary_class"] == "PR - English Literature"

    def test_keeps_template_when_book_has_no_description(self):
        books = [Book(id=1, title="X", authors=["Y"])]
        sug = _catalog_suggestion(1)
        original = sug.proposed["lcc_summary"]
        ai = _StubAI(result={1: "AI prose that should NOT appear"})

        _apply_ai_summary_to_catalog_hits(ai, books, [sug], {}, batch_size=10)

        # No description → AI not called.
        assert ai.call_count == 0
        # Template summary preserved.
        assert sug.proposed["lcc_summary"] == original

    def test_keeps_template_when_description_text_is_empty(self):
        books = [Book(id=1, title="X", authors=["Y"])]
        sug = _catalog_suggestion(1)
        original = sug.proposed["lcc_summary"]
        descs = {1: BookDescription(text="", source="OL", categories=[])}
        ai = _StubAI(result={1: "should not appear"})

        _apply_ai_summary_to_catalog_hits(ai, books, [sug], descs, batch_size=10)

        assert ai.call_count == 0
        assert sug.proposed["lcc_summary"] == original

    def test_mixed_batch_only_books_with_descriptions_go_through_ai(self):
        books = [
            Book(id=1, title="With desc", authors=["X"]),
            Book(id=2, title="No desc", authors=["Y"]),
        ]
        sug1 = _catalog_suggestion(1)
        sug2 = _catalog_suggestion(2)
        sug2_template = sug2.proposed["lcc_summary"]
        descs = {1: BookDescription(text="d1", source="OL", categories=[])}
        ai = _StubAI(result={1: "AI prose for 1"})

        _apply_ai_summary_to_catalog_hits(ai, books, [sug1, sug2], descs, batch_size=10)

        assert ai.call_count == 1
        # AI only saw book 1.
        assert len(ai.last_books) == 1
        assert ai.last_books[0].id == 1
        assert sug1.proposed["lcc_summary"] == "AI prose for 1"
        assert sug2.proposed["lcc_summary"] == sug2_template

    def test_ai_failure_keeps_template_summaries(self):
        books = [Book(id=1, title="X", authors=["Y"])]
        sug = _catalog_suggestion(1)
        original = sug.proposed["lcc_summary"]
        descs = {1: BookDescription(text="d", source="OL", categories=[])}
        ai = _StubAI(raise_exc=RuntimeError("AI broken"))

        # Must NOT raise — failure falls back to template.
        _apply_ai_summary_to_catalog_hits(ai, books, [sug], descs, batch_size=10)
        assert sug.proposed["lcc_summary"] == original

    def test_identity_mismatch_keeps_template_for_that_book(self):
        # AI returns the book in the result dict but with empty prose
        # (identity mismatch). In practice suggest_lcc_summary filters
        # empty entries OUT of the returned dict — emulate that here.
        books = [Book(id=1, title="X", authors=["Y"]),
                 Book(id=2, title="Z", authors=["W"])]
        sug1 = _catalog_suggestion(1)
        sug2 = _catalog_suggestion(2)
        sug2_template = sug2.proposed["lcc_summary"]
        descs = {bid: BookDescription(text=f"d{bid}", source="OL", categories=[]) for bid in (1, 2)}
        ai = _StubAI(result={1: "Real prose for 1"})  # 2 absent → identity mismatch

        _apply_ai_summary_to_catalog_hits(ai, books, [sug1, sug2], descs, batch_size=10)

        assert sug1.proposed["lcc_summary"] == "Real prose for 1"
        assert sug2.proposed["lcc_summary"] == sug2_template

    def test_no_op_when_catalog_suggestions_empty(self):
        ai = _StubAI()
        _apply_ai_summary_to_catalog_hits(ai, [], [], {}, batch_size=10)
        assert ai.call_count == 0

    def test_passes_catalog_source_into_ai_context(self):
        books = [Book(id=1, title="X", authors=["Y"])]
        sug = _catalog_suggestion(
            1, source="Open Library via edition cascade (seed ISBN 9781504026758, matched sibling 9780671254834)",
        )
        descs = {1: BookDescription(text="d", source="OL", categories=[])}
        ai = _StubAI(result={1: "AI prose"})

        _apply_ai_summary_to_catalog_hits(ai, books, [sug], descs, batch_size=10)

        assert ai.last_context[1]["catalog_source"].startswith("Open Library via edition cascade")
