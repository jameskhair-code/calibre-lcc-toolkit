"""Tests for services.lc_catalog response parsers.

The HTTP layer is stubbed out via monkeypatch — fixtures are recorded JSON
responses from LC and Open Library, so the suite never touches the network.
"""

import json
from pathlib import Path

import pytest

from calibre_toolkit.services import lc_catalog
from calibre_toolkit.services.lc_catalog import (
    CatalogHit,
    _normalise_lccn,
    _pick_lcc_call_number,
    lookup_book,
    lookup_by_isbn,
    lookup_by_isbn_openlibrary,
    lookup_by_lccn,
)


def _load_fixture(fixtures_dir: Path, name: str) -> dict:
    return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))


@pytest.fixture
def stub_http(monkeypatch, fixtures_dir):
    """Patch _http_get_json so each URL substring returns a fixture file."""
    routes: dict[str, dict | None] = {}

    def add_route(url_substring: str, fixture: str | None):
        if fixture is None:
            routes[url_substring] = None
        else:
            routes[url_substring] = _load_fixture(fixtures_dir, fixture)

    def fake_get(url: str, timeout=10.0):
        for sub, response in routes.items():
            if sub in url:
                return response
        return None

    monkeypatch.setattr(lc_catalog, "_http_get_json", fake_get)
    return add_route


class TestNormaliseLccn:
    @pytest.mark.parametrize("inp,want", [
        ("2024-012345", "2024012345"),
        (" n2024012345 ", "n2024012345"),
        ("87 - 12345", "87-12345".replace("-", "")),
        ("", ""),
    ])
    def test_strips_whitespace_and_hyphens(self, inp, want):
        assert _normalise_lccn(inp) == want


class TestPickCallNumber:
    def test_picks_lcc_pattern_over_other(self):
        # LC records can carry Dewey and other notes; we only want LCC.
        assert _pick_lcc_call_number(
            ["823.914", "PR6059.S5 R4 1989", "MARC holding note"]
        ) == "PR6059.S5 R4 1989"

    def test_empty_returns_none(self):
        assert _pick_lcc_call_number([]) is None

    def test_non_string_skipped(self):
        assert _pick_lcc_call_number([None, 123, "PS3563.O8749 B4 1987"]) == \
            "PS3563.O8749 B4 1987"

    def test_no_lcc_returns_none(self):
        # Pure Dewey list → None
        assert _pick_lcc_call_number(["823.914", "12 / DEW"]) is None


class TestLookupByLccn:
    def test_hit_returns_catalog_hit(self, stub_http):
        stub_http("/item/2024012345", "lc_item_hit.json")
        hit = lookup_by_lccn("2024-012345")
        assert isinstance(hit, CatalogHit)
        assert hit.call_number == "PS3563.O8749 B4 1987"
        assert hit.raw_lccn == "2024012345"
        assert "LC catalog" in hit.source

    def test_miss_returns_none(self, stub_http):
        stub_http("/item/", "lc_item_no_call_number.json")
        assert lookup_by_lccn("0000000000") is None

    def test_empty_lccn_returns_none(self, stub_http):
        assert lookup_by_lccn("") is None

    def test_http_failure_returns_none(self, stub_http):
        stub_http("/item/", None)
        assert lookup_by_lccn("2024012345") is None


class TestLookupByIsbn:
    def test_hit_returns_catalog_hit(self, stub_http):
        stub_http("/books/", "lc_books_hit.json")
        hit = lookup_by_isbn("9780571258246")
        assert hit is not None
        assert hit.call_number == "PR6059.S5 R4 1989"

    def test_empty_results_returns_none(self, stub_http):
        stub_http("/books/", "lc_books_empty.json")
        assert lookup_by_isbn("0000000000") is None

    def test_isbn_with_hyphens_normalised(self, stub_http):
        stub_http("/books/", "lc_books_hit.json")
        assert lookup_by_isbn("978-0-571-25824-6") is not None


class TestLookupByOpenLibrary:
    def test_hit_returns_catalog_hit(self, stub_http):
        stub_http("openlibrary.org", "openlibrary_hit.json")
        hit = lookup_by_isbn_openlibrary("9780571258246")
        assert hit is not None
        assert hit.call_number == "PR6059.S5 N48 2005"
        assert "Open Library" in hit.source

    def test_missing_classifications_returns_none(self, stub_http, fixtures_dir, monkeypatch):
        # Empty response → record exists but no LC classifications.
        monkeypatch.setattr(lc_catalog, "_http_get_json",
                            lambda url, timeout=10: {"ISBN:9780000000000": {}})
        assert lookup_by_isbn_openlibrary("9780000000000") is None


class TestLookupBookCascade:
    """lookup_book should walk LCCN → LC-ISBN → OL-ISBN in order."""

    def test_prefers_lccn(self, stub_http):
        # All three sources are wired — LCCN wins.
        stub_http("/item/", "lc_item_hit.json")
        stub_http("/books/", "lc_books_hit.json")
        stub_http("openlibrary.org", "openlibrary_hit.json")
        hit = lookup_book({"lccn": "2024012345", "isbn": "9780571258246"})
        assert hit is not None
        assert hit.call_number == "PS3563.O8749 B4 1987"
        assert "LCCN" in hit.source

    def test_falls_through_to_isbn(self, stub_http):
        stub_http("/books/", "lc_books_hit.json")
        stub_http("openlibrary.org", "openlibrary_hit.json")
        hit = lookup_book({"isbn": "9780571258246"})
        assert hit is not None
        assert hit.call_number == "PR6059.S5 R4 1989"  # LC wins over OL

    def test_falls_through_to_openlibrary(self, stub_http):
        stub_http("openlibrary.org", "openlibrary_hit.json")
        # LC misses (no route set → fake_get returns None for those URLs)
        hit = lookup_book({"isbn": "9780571258246"})
        assert hit is not None
        assert "Open Library" in hit.source

    def test_no_identifiers_returns_none(self, stub_http):
        assert lookup_book({}) is None

    def test_all_misses_returns_none(self, stub_http):
        # No routes wired → every call returns None
        assert lookup_book({"isbn": "9780000000000"}) is None
