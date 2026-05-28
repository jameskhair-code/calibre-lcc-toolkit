"""Tests for services.lc_catalog (Open Library-only after v1.3 LC removal).

The HTTP layer is stubbed via monkeypatch — fixtures are recorded JSON
responses, so the suite never touches the network.

Historical LC tests (lookup_by_lccn, lookup_by_isbn, SRU, MARCXML
parsing) were removed when those code paths were deleted; see
docs/LC-Cloudflare-Investigation.md for the rationale.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from calibre_toolkit.services import lc_catalog
from calibre_toolkit.services.lc_catalog import (
    CatalogHit,
    _lookup_isbns_openlibrary_batch,
    _ol_sibling_isbns_for_work,
    _ol_work_key_for_isbn,
    _pick_lcc_call_number,
    _workkey_cache_lookup,
    _workkey_cache_path,
    _workkey_cache_store,
    lookup_book,
    lookup_by_isbn_openlibrary,
    lookup_by_isbn_with_edition_cascade,
    reset_work_editions_cache,
    reset_workkey_cache,
)


def _load_fixture(fixtures_dir: Path, name: str) -> dict:
    return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _reset_caches(tmp_path, monkeypatch):
    """Both lc_catalog caches reset between tests; the persistent work-key
    cache file is redirected to a per-test tmp path so no test ever writes
    to the user's real ~/.calibre-toolkit/ol-workkey-cache.json."""
    monkeypatch.setenv(
        "CALIBRE_TOOLKIT_OL_WORKKEY_CACHE",
        str(tmp_path / "ol-workkey-cache.json"),
    )
    reset_work_editions_cache()
    reset_workkey_cache()
    yield
    reset_work_editions_cache()
    reset_workkey_cache()


@pytest.fixture
def stub_http(monkeypatch, fixtures_dir):
    """Patch _http_get_json so each URL substring returns a fixture file
    (or an inline dict, for ad-hoc test data)."""
    routes: dict[str, dict | None] = {}

    def add_route(url_substring: str, fixture: str | dict | None):
        if fixture is None:
            routes[url_substring] = None
        elif isinstance(fixture, dict):
            routes[url_substring] = fixture
        else:
            routes[url_substring] = _load_fixture(fixtures_dir, fixture)

    def fake_get(url: str, timeout=10.0, max_retries=3, treat_4xx_as_empty=False):
        for sub, response in routes.items():
            if sub in url:
                return response
        return None

    monkeypatch.setattr(lc_catalog, "_http_get_json", fake_get)
    return add_route


# ── _pick_lcc_call_number ───────────────────────────────────────────────────


class TestPickCallNumber:
    @pytest.mark.parametrize("inp,want", [
        (["PR9619.3.K46 C66 1979"], "PR9619.3.K46 C66 1979"),
        (["PS3563.O8749"], "PS3563.O8749"),
        (["DK189 .W67 2003"], "DK189 .W67 2003"),
    ])
    def test_picks_lcc_shaped_strings(self, inp, want):
        assert _pick_lcc_call_number(inp) == want

    def test_skips_non_lcc_strings(self):
        # Pure-decimal Dewey, plain narrative notes, etc. should be
        # skipped in favour of LCC.
        result = _pick_lcc_call_number(["813.54", "Includes index.", "PR9619.3.K46"])
        assert result == "PR9619.3.K46"

    def test_returns_none_for_empty_list(self):
        assert _pick_lcc_call_number([]) is None

    def test_returns_none_when_nothing_lcc_shaped(self):
        assert _pick_lcc_call_number(["813.54", "not a call number"]) is None

    def test_strips_leading_non_letters(self):
        # Some records prefix the call number with brackets.
        assert _pick_lcc_call_number(["[PR6063.C4 C66]"]) == "PR6063.C4 C66"


# ── Open Library direct ISBN lookup ─────────────────────────────────────────


class TestOpenLibraryDirect:
    def test_returns_hit_when_classifications_present(self, stub_http):
        stub_http("openlibrary.org/api/books?", "openlibrary_hit.json")
        # Fixture is keyed by ISBN 9780571258246.
        hit = lookup_by_isbn_openlibrary("9780571258246")
        assert hit is not None
        assert hit.call_number == "PR6059.S5 N48 2005"
        assert "Open Library" in hit.source

    def test_returns_none_when_no_classifications(self, stub_http):
        stub_http("openlibrary.org/api/books?", {"ISBN:9780000000000": {}})
        assert lookup_by_isbn_openlibrary("9780000000000") is None

    def test_returns_none_when_isbn_empty(self):
        assert lookup_by_isbn_openlibrary("") is None
        assert lookup_by_isbn_openlibrary("   ") is None

    def test_strips_isbn_hyphens_in_request(self, stub_http):
        stub_http("openlibrary.org/api/books?", "openlibrary_hit.json")
        # The fixture key is "ISBN:9780571258246"; hyphenated input
        # must reach the same record.
        hit = lookup_by_isbn_openlibrary("978-0-571-25824-6")
        assert hit is not None


# ── Batched bibkeys lookup ──────────────────────────────────────────────────


class TestBatchedBibkeys:
    """v1.7 item 3: one /api/books?bibkeys=ISBN:X,ISBN:Y,... call per
    sibling group, not one per sibling."""

    def test_single_isbn_returns_hit(self, stub_http):
        stub_http("openlibrary.org/api/books?", "openlibrary_hit.json")
        results = _lookup_isbns_openlibrary_batch(["9780571258246"])
        assert results["9780571258246"] is not None
        assert results["9780571258246"].call_number == "PR6059.S5 N48 2005"

    def test_returns_per_input_dict_with_hits_and_misses(self, stub_http):
        stub_http("openlibrary.org/api/books?", {
            "ISBN:9780000000001": {
                "classifications": {"lc_classifications": ["PR9619.3.K46"]},
            },
            "ISBN:9780000000002": {},
            # ISBN:9780000000003 absent from response — represents an
            # ISBN OL doesn't know at all.
        })
        results = _lookup_isbns_openlibrary_batch([
            "9780000000001", "9780000000002", "9780000000003",
        ])
        assert results["9780000000001"] is not None
        assert results["9780000000001"].call_number == "PR9619.3.K46"
        assert results["9780000000002"] is None
        assert results["9780000000003"] is None

    def test_single_http_call_for_whole_batch(self, monkeypatch):
        """N ISBNs → one HTTP request, not N."""
        call_count = 0

        def counting_get(url, timeout=10.0, max_retries=3, treat_4xx_as_empty=False):
            nonlocal call_count
            call_count += 1
            return {"ISBN:9780000000001": {}}

        monkeypatch.setattr(lc_catalog, "_http_get_json", counting_get)
        _lookup_isbns_openlibrary_batch([
            "9780000000001", "9780000000002", "9780000000003", "9780000000004",
        ])
        assert call_count == 1

    def test_url_carries_comma_separated_bibkeys(self, monkeypatch):
        captured: list[str] = []

        def capturing_get(url, timeout=10.0, max_retries=3):
            captured.append(url)
            return {}

        monkeypatch.setattr(lc_catalog, "_http_get_json", capturing_get)
        _lookup_isbns_openlibrary_batch(["9780000000001", "9780000000002"])
        assert len(captured) == 1
        # urlencode renders comma as %2C and colon as %3A.
        assert "ISBN%3A9780000000001%2CISBN%3A9780000000002" in captured[0]

    def test_strips_hyphens_and_whitespace_for_url(self, monkeypatch):
        captured: list[str] = []

        def capturing_get(url, timeout=10.0, max_retries=3):
            captured.append(url)
            return {
                "ISBN:9780000000001": {
                    "classifications": {"lc_classifications": ["PR1"]},
                },
            }

        monkeypatch.setattr(lc_catalog, "_http_get_json", capturing_get)
        results = _lookup_isbns_openlibrary_batch(["978-0-00-000000-1"])
        assert "ISBN%3A9780000000001" in captured[0]
        # Result is keyed by the original input string, not the cleaned form.
        assert results["978-0-00-000000-1"] is not None
        assert results["978-0-00-000000-1"].call_number == "PR1"

    def test_dedupes_inputs_in_url_but_preserves_keys(self, monkeypatch):
        captured: list[str] = []

        def capturing_get(url, timeout=10.0, max_retries=3):
            captured.append(url)
            return {
                "ISBN:9780000000001": {
                    "classifications": {"lc_classifications": ["PR1"]},
                },
            }

        monkeypatch.setattr(lc_catalog, "_http_get_json", capturing_get)
        results = _lookup_isbns_openlibrary_batch([
            "9780000000001", "9780000000001",
        ])
        # Duplicate doesn't expand into two bibkeys entries.
        assert captured[0].count("ISBN%3A9780000000001") == 1
        assert results["9780000000001"] is not None

    def test_skips_blank_and_none_inputs(self, monkeypatch):
        captured: list[str] = []

        def capturing_get(url, timeout=10.0, max_retries=3):
            captured.append(url)
            return {
                "ISBN:9780000000001": {
                    "classifications": {"lc_classifications": ["PR1"]},
                },
            }

        monkeypatch.setattr(lc_catalog, "_http_get_json", capturing_get)
        results = _lookup_isbns_openlibrary_batch(["", "   ", "9780000000001"])
        assert "ISBN%3A9780000000001" in captured[0]
        assert results[""] is None
        assert results["   "] is None
        assert results["9780000000001"] is not None

    def test_empty_input_makes_no_http_call(self, monkeypatch):
        call_count = 0

        def counting_get(url, timeout=10.0, max_retries=3, treat_4xx_as_empty=False):
            nonlocal call_count
            call_count += 1
            return None

        monkeypatch.setattr(lc_catalog, "_http_get_json", counting_get)
        assert _lookup_isbns_openlibrary_batch([]) == {}
        assert _lookup_isbns_openlibrary_batch(["", "   "]) == {"": None, "   ": None}
        assert call_count == 0

    def test_http_failure_returns_all_none(self, monkeypatch):
        def failing_get(url, timeout=10.0, max_retries=3):
            return None

        monkeypatch.setattr(lc_catalog, "_http_get_json", failing_get)
        results = _lookup_isbns_openlibrary_batch([
            "9780000000001", "9780000000002",
        ])
        assert results == {"9780000000001": None, "9780000000002": None}


# ── OL work-key resolution ──────────────────────────────────────────────────


class TestWorkKey:
    def test_returns_work_key_when_present(self, stub_http):
        stub_http("openlibrary.org/isbn/9781504026758.json",
                  "ol_isbn_lookup_with_work.json")
        assert _ol_work_key_for_isbn("9781504026758") == "/works/OL999W"

    def test_returns_none_when_no_work_field(self, stub_http):
        stub_http("openlibrary.org/isbn/9780000000001.json",
                  "ol_isbn_lookup_no_work.json")
        assert _ol_work_key_for_isbn("9780000000001") is None

    def test_returns_none_on_empty_isbn(self):
        assert _ol_work_key_for_isbn("") is None
        assert _ol_work_key_for_isbn("   ") is None

    def test_returns_none_when_http_fails(self, stub_http):
        assert _ol_work_key_for_isbn("9780000000001") is None

    def test_strips_isbn_hyphens(self, stub_http):
        stub_http("9781504026758", "ol_isbn_lookup_with_work.json")
        assert _ol_work_key_for_isbn("978-1-504-02675-8") == "/works/OL999W"


# ── Persistent work-key cache ───────────────────────────────────────────────


class TestPersistentWorkKeyCache:
    """v1.7 item 4: ISBN -> work_key resolution persists across runs at
    ~/.calibre-toolkit/ol-workkey-cache.json (90-day TTL). The autouse
    `_reset_caches` fixture redirects the cache file to tmp_path."""

    def test_env_override_redirects_cache_file(self, tmp_path, monkeypatch):
        custom = tmp_path / "custom" / "cache.json"
        monkeypatch.setenv("CALIBRE_TOOLKIT_OL_WORKKEY_CACHE", str(custom))
        assert _workkey_cache_path() == custom

    def test_cold_lookup_calls_http_then_persists_positive(self, stub_http, tmp_path):
        stub_http("openlibrary.org/isbn/9781504026758.json",
                  "ol_isbn_lookup_with_work.json")
        # Cold — no cache file exists yet.
        assert not _workkey_cache_path().exists()
        result = _ol_work_key_for_isbn("9781504026758")
        assert result == "/works/OL999W"
        # File should now exist with the entry.
        assert _workkey_cache_path().exists()
        payload = json.loads(_workkey_cache_path().read_text(encoding="utf-8"))
        assert payload["version"] == 1
        assert payload["entries"]["9781504026758"]["work_key"] == "/works/OL999W"

    def test_cold_lookup_persists_negative(self, stub_http):
        stub_http("openlibrary.org/isbn/9780000000001.json",
                  "ol_isbn_lookup_no_work.json")
        assert _ol_work_key_for_isbn("9780000000001") is None
        payload = json.loads(_workkey_cache_path().read_text(encoding="utf-8"))
        assert payload["entries"]["9780000000001"]["work_key"] is None

    def test_warm_hit_skips_http_positive(self, monkeypatch):
        # Pre-populate cache directly.
        _workkey_cache_store("9781504026758", "/works/OL999W")
        # Any HTTP call would fail the test.
        def explode(url, timeout=10.0, max_retries=3):
            raise AssertionError(f"HTTP must not be called when cache is warm: {url}")
        monkeypatch.setattr(lc_catalog, "_http_get_json", explode)
        assert _ol_work_key_for_isbn("9781504026758") == "/works/OL999W"

    def test_warm_hit_skips_http_negative(self, monkeypatch):
        _workkey_cache_store("9780000000001", None)
        def explode(url, timeout=10.0, max_retries=3):
            raise AssertionError(f"HTTP must not be called for negative cached entry: {url}")
        monkeypatch.setattr(lc_catalog, "_http_get_json", explode)
        assert _ol_work_key_for_isbn("9780000000001") is None

    def test_stale_entry_past_ttl_triggers_refetch(self, stub_http):
        from datetime import datetime, timedelta, timezone
        stale = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat(timespec="seconds")
        _workkey_cache_path().parent.mkdir(parents=True, exist_ok=True)
        _workkey_cache_path().write_text(json.dumps({
            "version": 1,
            "entries": {
                "9781504026758": {"work_key": "/works/OLstale", "fetched_at": stale},
            },
        }), encoding="utf-8")
        # In-memory mirror is None (reset by autouse fixture) — first lookup
        # loads from disk, finds the stale entry, and refetches.
        stub_http("openlibrary.org/isbn/9781504026758.json",
                  "ol_isbn_lookup_with_work.json")
        assert _ol_work_key_for_isbn("9781504026758") == "/works/OL999W"
        payload = json.loads(_workkey_cache_path().read_text(encoding="utf-8"))
        assert payload["entries"]["9781504026758"]["work_key"] == "/works/OL999W"

    def test_http_failure_does_not_poison_cache(self, monkeypatch):
        # _http_get_json returning None mimics retry-exhausted transient failure.
        monkeypatch.setattr(
            lc_catalog, "_http_get_json",
            lambda url, timeout=10.0, max_retries=3, treat_4xx_as_empty=False: None,
        )
        assert _ol_work_key_for_isbn("9780000000002") is None
        # No entry should have been persisted — next run can retry.
        if _workkey_cache_path().exists():
            payload = json.loads(_workkey_cache_path().read_text(encoding="utf-8"))
            assert "9780000000002" not in (payload.get("entries") or {})

    def test_ol_404_cached_as_negative(self, monkeypatch):
        """When _http_get_json signals a definite 404 by returning {}
        (via treat_4xx_as_empty=True), the work-key resolver caches
        the result as negative so the next run skips the HTTP call."""
        call_count = 0

        def fake_get_404(url, timeout=10.0, max_retries=3, treat_4xx_as_empty=False):
            nonlocal call_count
            if "openlibrary.org/isbn/9780000000003.json" in url:
                call_count += 1
                # treat_4xx_as_empty=True is set by _ol_work_key_for_isbn.
                # Return {} to simulate OL's 404 for an unknown ISBN.
                return {} if treat_4xx_as_empty else None
            return None

        monkeypatch.setattr(lc_catalog, "_http_get_json", fake_get_404)
        # First call: HTTP fires, result cached as negative.
        assert _ol_work_key_for_isbn("9780000000003") is None
        assert call_count == 1
        # Persisted as negative.
        payload = json.loads(_workkey_cache_path().read_text(encoding="utf-8"))
        assert "9780000000003" in payload["entries"]
        assert payload["entries"]["9780000000003"]["work_key"] is None
        # Second call: cache hit, no HTTP.
        assert _ol_work_key_for_isbn("9780000000003") is None
        assert call_count == 1

    def test_corrupt_cache_file_degrades_gracefully(self, stub_http):
        _workkey_cache_path().parent.mkdir(parents=True, exist_ok=True)
        _workkey_cache_path().write_text("{not valid json", encoding="utf-8")
        stub_http("openlibrary.org/isbn/9781504026758.json",
                  "ol_isbn_lookup_with_work.json")
        # Must not raise; corrupt file is treated as empty.
        assert _ol_work_key_for_isbn("9781504026758") == "/works/OL999W"

    def test_unknown_schema_version_degrades_gracefully(self, stub_http):
        _workkey_cache_path().parent.mkdir(parents=True, exist_ok=True)
        _workkey_cache_path().write_text(json.dumps({
            "version": 999,
            "entries": {"9781504026758": {"work_key": "/works/IGNORED",
                                          "fetched_at": "2099-01-01T00:00:00+00:00"}},
        }), encoding="utf-8")
        stub_http("openlibrary.org/isbn/9781504026758.json",
                  "ol_isbn_lookup_with_work.json")
        # Must not honour the unknown-version entries.
        assert _ol_work_key_for_isbn("9781504026758") == "/works/OL999W"

    def test_missing_cache_file_starts_empty(self):
        assert not _workkey_cache_path().exists()
        hit, cached = _workkey_cache_lookup("9781504026758")
        assert hit is False
        assert cached is None

    def test_hyphenated_isbn_matches_cleaned_cache_key(self, monkeypatch):
        _workkey_cache_store("9781504026758", "/works/OL999W")
        monkeypatch.setattr(lc_catalog, "_http_get_json",
                            lambda url, **kw: pytest.fail("HTTP unexpected"))
        assert _ol_work_key_for_isbn("978-1-504-02675-8") == "/works/OL999W"

    def test_second_lookup_in_same_run_skips_http(self, monkeypatch):
        call_count = 0

        def counting_get(url, timeout=10.0, max_retries=3, treat_4xx_as_empty=False):
            nonlocal call_count
            if "openlibrary.org/isbn/9781504026758.json" in url:
                call_count += 1
                return {"works": [{"key": "/works/OL999W"}]}
            return None

        monkeypatch.setattr(lc_catalog, "_http_get_json", counting_get)
        assert _ol_work_key_for_isbn("9781504026758") == "/works/OL999W"
        # Second call within the same process — must come from the cache.
        assert _ol_work_key_for_isbn("9781504026758") == "/works/OL999W"
        assert call_count == 1


# ── OL sibling ISBN enumeration ─────────────────────────────────────────────


class TestSiblingIsbns:
    def test_returns_siblings_excluding_seed(self, stub_http):
        stub_http("/works/OL999W/editions.json", "ol_work_editions.json")
        siblings = _ol_sibling_isbns_for_work("/works/OL999W", "9781504026758")
        assert "9781504026758" not in siblings
        assert "9780671254834" in siblings
        assert "0671254839" in siblings
        # English-language editions ranked ahead of the German.
        assert siblings.index("9780671254834") < siblings.index("9783000000007")

    def test_returns_empty_when_no_entries(self, stub_http):
        stub_http("/works/OL999W/editions.json", "ol_work_editions_empty.json")
        assert _ol_sibling_isbns_for_work("/works/OL999W", "9781504026758") == []

    def test_returns_empty_when_work_key_invalid(self):
        assert _ol_sibling_isbns_for_work("", "9780000000001") == []
        assert _ol_sibling_isbns_for_work("not-a-key", "9780000000001") == []

    def test_caps_at_max_isbns(self, stub_http):
        many_entries = {
            "entries": [
                {
                    "isbn_13": [f"978000000{i:04d}"],
                    "languages": [{"key": "/languages/eng"}],
                }
                for i in range(50)
            ]
        }
        stub_http("/works/OL_BIG/editions.json", many_entries)
        siblings = _ol_sibling_isbns_for_work(
            "/works/OL_BIG", excluded_isbn="9780000000099", max_isbns=5,
        )
        assert len(siblings) == 5

    def test_default_cap_is_10(self):
        """Item 12a / probe outcome: cap raised from 3 → 10 after the
        deeper walk proved it lifts hit rate from 27% → 76% on books
        with ISBNs. Lower it again only with new evidence."""
        from calibre_toolkit.services.lc_catalog import _EDITION_CASCADE_MAX_ISBNS
        assert _EDITION_CASCADE_MAX_ISBNS == 10


# ── Work-editions cache ─────────────────────────────────────────────────────


class TestWorkEditionsCache:
    def test_repeated_calls_for_same_work_hit_http_once(self, monkeypatch, fixtures_dir):
        """Several books in the same series share an OL work; the cache
        means we only fetch the editions list once per process."""
        call_count = 0
        editions = _load_fixture(fixtures_dir, "ol_work_editions.json")

        def counting_get(url, timeout=10.0, max_retries=3, treat_4xx_as_empty=False):
            nonlocal call_count
            if "/works/OL999W/editions.json" in url:
                call_count += 1
                return editions
            return None

        monkeypatch.setattr(lc_catalog, "_http_get_json", counting_get)

        # First call populates the cache.
        siblings_1 = _ol_sibling_isbns_for_work("/works/OL999W", "9781504026758")
        # Subsequent calls (potentially from another book in the series
        # mapping to the same work) re-use it.
        siblings_2 = _ol_sibling_isbns_for_work("/works/OL999W", "9781504026758")
        siblings_3 = _ol_sibling_isbns_for_work("/works/OL999W", "9780671254834")
        assert call_count == 1
        assert siblings_1 == siblings_2
        # Different exclusion still works from cached entries.
        assert "9780671254834" not in siblings_3
        assert "9781504026758" in siblings_3

    def test_reset_clears_cache(self, monkeypatch, fixtures_dir):
        editions = _load_fixture(fixtures_dir, "ol_work_editions.json")
        call_count = 0

        def counting_get(url, timeout=10.0, max_retries=3, treat_4xx_as_empty=False):
            nonlocal call_count
            if "editions.json" in url:
                call_count += 1
                return editions
            return None

        monkeypatch.setattr(lc_catalog, "_http_get_json", counting_get)

        _ol_sibling_isbns_for_work("/works/OL999W", "9781504026758")
        assert call_count == 1
        reset_work_editions_cache()
        _ol_sibling_isbns_for_work("/works/OL999W", "9781504026758")
        assert call_count == 2


# ── End-to-end edition cascade ──────────────────────────────────────────────


class TestEditionCascade:
    def test_returns_hit_when_sibling_isbn_has_classifications(self, stub_http):
        stub_http("openlibrary.org/isbn/9781504026758.json",
                  "ol_isbn_lookup_with_work.json")
        stub_http("/works/OL999W/editions.json", "ol_work_editions.json")
        # The US sibling 9780671254834 has classifications. Inline so
        # the key on the response matches what the cascade asks for.
        stub_http(
            "openlibrary.org/api/books?bibkeys=ISBN%3A9780671254834",
            {"ISBN:9780671254834": {
                "classifications": {"lc_classifications": ["PR9619.3.K46 C66"]},
            }},
        )

        hit = lookup_by_isbn_with_edition_cascade("9781504026758")
        assert hit is not None
        assert "edition cascade" in hit.source
        assert "9780671254834" in hit.source

    def test_returns_none_when_no_sibling_hits(self, stub_http):
        stub_http("openlibrary.org/isbn/9781504026758.json",
                  "ol_isbn_lookup_with_work.json")
        stub_http("/works/OL999W/editions.json", "ol_work_editions.json")
        # No OL-direct fixture wired → every sibling lookup returns None.
        hit = lookup_by_isbn_with_edition_cascade("9781504026758")
        assert hit is None

    def test_returns_none_when_no_work_key(self, stub_http):
        stub_http("openlibrary.org/isbn/9780000000001.json",
                  "ol_isbn_lookup_no_work.json")
        assert lookup_by_isbn_with_edition_cascade("9780000000001") is None

    def test_returns_none_on_empty_isbn(self):
        assert lookup_by_isbn_with_edition_cascade("") is None

    def test_sibling_lookup_is_one_http_call(self, monkeypatch, fixtures_dir):
        """v1.7 item 3: sibling classifications resolve in ONE batched
        bibkeys request, not one per sibling. Pre-v1.7 this would have
        been three sequential /api/books? calls."""
        editions = _load_fixture(fixtures_dir, "ol_work_editions.json")
        isbn_lookup = _load_fixture(fixtures_dir, "ol_isbn_lookup_with_work.json")
        api_books_calls = 0

        def counting_get(url, timeout=10.0, max_retries=3, treat_4xx_as_empty=False):
            nonlocal api_books_calls
            if "openlibrary.org/api/books?" in url:
                api_books_calls += 1
                # First sibling gets classifications; the rest don't.
                return {
                    "ISBN:9780671254834": {
                        "classifications": {"lc_classifications": ["PR9619.3.K46 C66"]},
                    },
                }
            if "openlibrary.org/isbn/9781504026758.json" in url:
                return isbn_lookup
            if "/works/OL999W/editions.json" in url:
                return editions
            return None

        monkeypatch.setattr(lc_catalog, "_http_get_json", counting_get)
        hit = lookup_by_isbn_with_edition_cascade("9781504026758")
        assert hit is not None
        # ol_work_editions.json has 3 sibling ISBNs after seed exclusion;
        # the pre-v1.7 implementation would have made up to 3 calls.
        assert api_books_calls == 1


# ── lookup_book end-to-end cascade ──────────────────────────────────────────


class TestLookupBookCascade:
    """After the v1.3 LC removal, lookup_book walks two paths:
       1. OL direct ISBN
       2. OL edition cascade (sibling ISBN walk)."""

    def test_direct_ol_isbn_wins_when_present(self, stub_http):
        stub_http("openlibrary.org/api/books?", "openlibrary_hit.json")
        # work / editions routes left unwired — they must not be consulted.
        hit = lookup_book({"isbn": "9780571258246"})
        assert hit is not None
        assert hit.source.startswith("Open Library")
        assert "edition cascade" not in hit.source

    def test_falls_through_to_edition_cascade(self, stub_http):
        """Direct OL lookup misses (the requested ISBN isn't in OL's data)
        but the work cascade finds a sibling that does."""
        # Direct OL lookup for the seed ISBN: empty response. URL is
        # built with urlencode which produces %3A for the colon.
        stub_http(
            "openlibrary.org/api/books?bibkeys=ISBN%3A9781504026758",
            {"ISBN:9781504026758": {}},
        )
        # OL knows the work and its editions.
        stub_http("openlibrary.org/isbn/9781504026758.json",
                  "ol_isbn_lookup_with_work.json")
        stub_http("/works/OL999W/editions.json", "ol_work_editions.json")
        # The US sibling 9780671254834 has classifications.
        stub_http(
            "openlibrary.org/api/books?bibkeys=ISBN%3A9780671254834",
            {"ISBN:9780671254834": {
                "classifications": {"lc_classifications": ["PR9619.3.K46 C66"]},
            }},
        )

        hit = lookup_book({"isbn": "9781504026758"})
        assert hit is not None
        assert "edition cascade" in hit.source

    def test_returns_none_when_every_path_misses(self, stub_http):
        stub_http("openlibrary.org/api/books?",
                  {"ISBN:9780000000001": {}})
        stub_http("openlibrary.org/isbn/", "ol_isbn_lookup_no_work.json")
        assert lookup_book({"isbn": "9780000000001"}) is None

    def test_returns_none_when_no_identifiers(self):
        assert lookup_book({}) is None
        assert lookup_book({}, title="X", author="Y") is None

    def test_title_and_author_accepted_for_signature_stability(self, stub_http):
        """The pre-v1.3 cascade fed title/author into LC SRU. SRU is
        gone, but the params remain accepted so callers don't break."""
        stub_http("openlibrary.org/api/books?", "openlibrary_hit.json")
        hit = lookup_book(
            {"isbn": "9780571258246"},
            title="Never Let Me Go",
            author="Kazuo Ishiguro",
        )
        assert hit is not None
