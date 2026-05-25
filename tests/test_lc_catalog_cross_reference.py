"""Tests for v1.3 item 12 — ISBN cross-reference for non-US editions.

Two new lookup paths plus a re-enabled one, all wired through the
unified `lookup_book` cascade:

  1. lookup_by_isbn_with_edition_cascade — OL work / editions graph walk
     to find sibling ISBNs, then retry LC ISBN lookup against them.
  2. lookup_by_title_author_sru — LC SRU title+author search of last
     resort, MARCXML parsing of the 050 datafield.
  3. lookup_book — now also surfaces OL hits (previously filtered out
     in modules/lcc.py:325 before item 11 gave us a real description
     pipeline).

All network calls are stubbed via the existing _http_get_json / new
_http_get_text monkeypatch hooks. Hermetic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from calibre_toolkit.services import lc_catalog
from calibre_toolkit.services.lc_catalog import (
    CatalogHit,
    _extract_call_number_from_marcxml,
    _ol_sibling_isbns_for_work,
    _ol_work_key_for_isbn,
    lookup_book,
    lookup_by_isbn_with_edition_cascade,
    lookup_by_title_author_sru,
)


def _load_text(fixtures_dir: Path, name: str) -> str:
    return (fixtures_dir / name).read_text(encoding="utf-8")


import json


def _load_json(fixtures_dir: Path, name: str) -> dict:
    return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))


@pytest.fixture
def stub_http_json(monkeypatch, fixtures_dir):
    """Same pattern as the existing stub_http fixture but local so this
    file can layer routes on top without colliding with other suites."""
    routes: dict[str, dict | None] = {}

    def add_route(url_substring: str, fixture: str | dict | None):
        if fixture is None:
            routes[url_substring] = None
        elif isinstance(fixture, dict):
            routes[url_substring] = fixture
        else:
            routes[url_substring] = _load_json(fixtures_dir, fixture)

    def fake_get(url: str, timeout=10.0, max_retries=3):
        for sub, response in routes.items():
            if sub in url:
                return response
        return None

    monkeypatch.setattr(lc_catalog, "_http_get_json", fake_get)
    return add_route


@pytest.fixture
def stub_http_text(monkeypatch, fixtures_dir):
    routes: dict[str, str | None] = {}

    def add_route(url_substring: str, fixture: str | None):
        if fixture is None:
            routes[url_substring] = None
        else:
            routes[url_substring] = _load_text(fixtures_dir, fixture)

    def fake_get(url: str, timeout=10.0, max_retries=3):
        for sub, response in routes.items():
            if sub in url:
                return response
        return None

    monkeypatch.setattr(lc_catalog, "_http_get_text", fake_get)
    return add_route


# ── OL work-key resolution ───────────────────────────────────────────────────


class TestOlWorkKey:
    def test_returns_work_key_when_present(self, stub_http_json):
        stub_http_json("openlibrary.org/isbn/9781504026758.json",
                       "ol_isbn_lookup_with_work.json")
        assert _ol_work_key_for_isbn("9781504026758") == "/works/OL999W"

    def test_returns_none_when_no_work_field(self, stub_http_json):
        stub_http_json("openlibrary.org/isbn/9780000000001.json",
                       "ol_isbn_lookup_no_work.json")
        assert _ol_work_key_for_isbn("9780000000001") is None

    def test_returns_none_on_empty_isbn(self):
        assert _ol_work_key_for_isbn("") is None
        assert _ol_work_key_for_isbn("   ") is None

    def test_returns_none_when_http_fails(self, stub_http_json):
        # No route configured → fake_get returns None for everything.
        assert _ol_work_key_for_isbn("9780000000001") is None

    def test_strips_isbn_hyphens(self, stub_http_json):
        stub_http_json("9781504026758", "ol_isbn_lookup_with_work.json")
        assert _ol_work_key_for_isbn("978-1-504-02675-8") == "/works/OL999W"


# ── OL sibling ISBN enumeration ──────────────────────────────────────────────


class TestSiblingIsbns:
    def test_returns_siblings_excluding_seed(self, stub_http_json):
        stub_http_json("/works/OL999W/editions.json", "ol_work_editions.json")
        siblings = _ol_sibling_isbns_for_work("/works/OL999W", "9781504026758")
        # Seed is filtered; the US first-edition siblings and German
        # ISBN should all appear (English ones first by preference).
        assert "9781504026758" not in siblings
        assert "9780671254834" in siblings
        assert "0671254839" in siblings
        # English-language editions ranked ahead of the German.
        idx_en = siblings.index("9780671254834")
        idx_de = siblings.index("9783000000007")
        assert idx_en < idx_de

    def test_returns_empty_when_no_entries(self, stub_http_json):
        stub_http_json("/works/OL999W/editions.json", "ol_work_editions_empty.json")
        assert _ol_sibling_isbns_for_work("/works/OL999W", "9781504026758") == []

    def test_returns_empty_when_work_key_invalid(self):
        assert _ol_sibling_isbns_for_work("", "9780000000001") == []
        assert _ol_sibling_isbns_for_work("not-a-key", "9780000000001") == []

    def test_caps_at_max_isbns(self, stub_http_json):
        # Fabricate a work with many editions in-memory; pass the dict
        # straight to the stub so we don't have to write a giant fixture.
        many_entries = {
            "entries": [
                {
                    "isbn_13": [f"978000000{i:04d}"],
                    "languages": [{"key": "/languages/eng"}],
                }
                for i in range(50)
            ]
        }
        stub_http_json("/works/OL_BIG/editions.json", many_entries)
        siblings = _ol_sibling_isbns_for_work(
            "/works/OL_BIG", excluded_isbn="9780000000099", max_isbns=5,
        )
        assert len(siblings) == 5


# ── End-to-end edition cascade ───────────────────────────────────────────────


class TestEditionCascade:
    def test_returns_hit_when_sibling_isbn_matches_lc(self, stub_http_json):
        stub_http_json("openlibrary.org/isbn/9781504026758.json",
                       "ol_isbn_lookup_with_work.json")
        stub_http_json("/works/OL999W/editions.json", "ol_work_editions.json")
        # The US first-edition ISBN hits LC.
        stub_http_json("loc.gov/books/?q=9780671254834",
                       "lc_books_hit.json")
        hit = lookup_by_isbn_with_edition_cascade("9781504026758")
        assert hit is not None
        assert "edition cascade" in hit.source
        assert "9780671254834" in hit.source

    def test_returns_none_when_no_sibling_isbn_hits(self, stub_http_json):
        stub_http_json("openlibrary.org/isbn/9781504026758.json",
                       "ol_isbn_lookup_with_work.json")
        stub_http_json("/works/OL999W/editions.json", "ol_work_editions.json")
        # No LC fixture for any sibling → all miss.
        stub_http_json("loc.gov/books/", "lc_books_empty.json")
        hit = lookup_by_isbn_with_edition_cascade("9781504026758")
        assert hit is None

    def test_returns_none_when_no_work_key(self, stub_http_json):
        stub_http_json("openlibrary.org/isbn/9780000000001.json",
                       "ol_isbn_lookup_no_work.json")
        assert lookup_by_isbn_with_edition_cascade("9780000000001") is None

    def test_returns_none_on_empty_isbn(self):
        assert lookup_by_isbn_with_edition_cascade("") is None


# ── MARCXML extraction ───────────────────────────────────────────────────────


class TestMarcxmlExtraction:
    def test_extracts_050_call_number(self, fixtures_dir):
        xml = _load_text(fixtures_dir, "lc_sru_hit.xml")
        call = _extract_call_number_from_marcxml(xml)
        assert call is not None
        assert call.startswith("PR9619.3.K46")

    def test_returns_none_when_no_050(self, fixtures_dir):
        xml = _load_text(fixtures_dir, "lc_sru_no_call_number.xml")
        assert _extract_call_number_from_marcxml(xml) is None

    def test_returns_none_when_empty_response(self, fixtures_dir):
        xml = _load_text(fixtures_dir, "lc_sru_empty.xml")
        assert _extract_call_number_from_marcxml(xml) is None

    def test_returns_none_on_malformed_xml(self):
        assert _extract_call_number_from_marcxml("not <xml>>") is None
        assert _extract_call_number_from_marcxml("") is None


# ── SRU title+author search ──────────────────────────────────────────────────


class TestSruSearch:
    def test_returns_hit_with_both_title_and_author(self, stub_http_text):
        stub_http_text("lx2.loc.gov/sru/", "lc_sru_hit.xml")
        hit = lookup_by_title_author_sru("Confederates", "Thomas Keneally")
        assert hit is not None
        assert hit.call_number.startswith("PR9619.3.K46")
        assert "LC SRU" in hit.source
        assert "Confederates" in hit.source

    def test_returns_none_when_title_missing(self, stub_http_text):
        # No HTTP call expected — should short-circuit on input validation.
        assert lookup_by_title_author_sru("", "Author") is None

    def test_returns_none_when_author_missing(self, stub_http_text):
        assert lookup_by_title_author_sru("Title", "") is None

    def test_returns_none_on_empty_response(self, stub_http_text):
        stub_http_text("lx2.loc.gov/sru/", "lc_sru_empty.xml")
        assert lookup_by_title_author_sru("X", "Y") is None

    def test_returns_none_when_no_call_number(self, stub_http_text):
        stub_http_text("lx2.loc.gov/sru/", "lc_sru_no_call_number.xml")
        assert lookup_by_title_author_sru("X", "Y") is None


# ── lookup_book end-to-end cascade ───────────────────────────────────────────


class TestLookupBookCascade:
    def test_direct_lc_isbn_wins_when_present(self, stub_http_json, stub_http_text):
        stub_http_json("loc.gov/books/?q=9781504026758", "lc_books_hit.json")
        # OL routes left unconfigured — they must not be consulted.
        hit = lookup_book({"isbn": "9781504026758"}, "Confederates", "Keneally")
        assert hit is not None
        assert "LC catalog" in hit.source
        assert "edition cascade" not in hit.source

    def test_falls_through_to_edition_cascade(self, stub_http_json, stub_http_text):
        # Seed ISBN misses LC directly.
        stub_http_json("loc.gov/books/?q=9781504026758", "lc_books_empty.json")
        # OL knows the work and its editions.
        stub_http_json("openlibrary.org/isbn/9781504026758.json",
                       "ol_isbn_lookup_with_work.json")
        stub_http_json("/works/OL999W/editions.json", "ol_work_editions.json")
        # The US sibling ISBN hits LC.
        stub_http_json("loc.gov/books/?q=9780671254834", "lc_books_hit.json")

        hit = lookup_book({"isbn": "9781504026758"}, "Confederates", "Keneally")
        assert hit is not None
        assert "edition cascade" in hit.source

    def test_falls_through_to_sru_when_all_isbn_paths_miss(self, stub_http_json, stub_http_text):
        # Every ISBN-driven lookup misses.
        stub_http_json("loc.gov/books/", "lc_books_empty.json")
        stub_http_json("openlibrary.org/isbn/", "ol_isbn_lookup_no_work.json")
        # SRU saves the day.
        stub_http_text("lx2.loc.gov/sru/", "lc_sru_hit.xml")

        hit = lookup_book(
            {"isbn": "9781504026758"}, "Confederates", "Thomas Keneally",
        )
        assert hit is not None
        assert "LC SRU" in hit.source

    def test_falls_through_to_open_library_as_last_resort(self, stub_http_json, stub_http_text):
        # Every LC path misses; no work key from OL ISBN lookup; SRU also miss.
        stub_http_json("loc.gov/books/", "lc_books_empty.json")
        stub_http_json("openlibrary.org/isbn/", "ol_isbn_lookup_no_work.json")
        stub_http_text("lx2.loc.gov/sru/", "lc_sru_empty.xml")
        # OL's separate /api/books endpoint has an LC classification.
        # The existing fixture is keyed by ISBN 9780571258246, so use that.
        stub_http_json("openlibrary.org/api/books?", "openlibrary_hit.json")

        hit = lookup_book(
            {"isbn": "9780571258246"}, "Never Let Me Go", "Kazuo Ishiguro",
        )
        assert hit is not None
        assert hit.source.startswith("Open Library")

    def test_returns_none_when_every_path_misses(self, stub_http_json, stub_http_text):
        stub_http_json("loc.gov/books/", "lc_books_empty.json")
        stub_http_json("openlibrary.org/isbn/", "ol_isbn_lookup_no_work.json")
        stub_http_text("lx2.loc.gov/sru/", "lc_sru_empty.xml")
        stub_http_json("openlibrary.org/api/books?", "lc_books_empty.json")
        assert lookup_book(
            {"isbn": "9780000000001"}, "Unknown", "Unknown",
        ) is None

    def test_returns_none_when_no_identifiers_and_no_title_author(self):
        assert lookup_book({}, "", "") is None

    def test_sru_skipped_when_title_or_author_missing(self, stub_http_json, stub_http_text):
        """SRU runs only when both title AND author are present."""
        stub_http_json("loc.gov/books/", "lc_books_empty.json")
        stub_http_json("openlibrary.org/isbn/", "ol_isbn_lookup_no_work.json")
        # SRU returns a hit, but we should not consult it.
        stub_http_text("lx2.loc.gov/sru/", "lc_sru_hit.xml")
        # OL direct ISBN is also empty.
        stub_http_json("openlibrary.org/api/books?", "lc_books_empty.json")

        hit = lookup_book({"isbn": "9780000000001"}, "Title", "")
        assert hit is None  # SRU was skipped, OL had nothing.
