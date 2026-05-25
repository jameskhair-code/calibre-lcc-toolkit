"""Tests for the publisher / community description pre-fetch service.

Item 11 (v1.3). Mocks the HTTP layer at urllib.request.urlopen so all
tests stay hermetic — no live API calls.
"""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from calibre_toolkit.services import book_description as bd

_FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _http_response(body: dict):
    """Build a fake urllib response yielding the given JSON body."""
    raw = json.dumps(body).encode("utf-8")
    fake = MagicMock()
    fake.status = 200
    fake.read.return_value = raw
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    return fake


# ── Normalisation + cleaning ─────────────────────────────────────────────────


def test_normalise_isbn_strips_hyphens_and_spaces():
    assert bd._normalise_isbn("978-0-394-72024-1") == "9780394720241"
    assert bd._normalise_isbn("  9780394720241 ") == "9780394720241"
    assert bd._normalise_isbn("") == ""
    assert bd._normalise_isbn(None) == ""  # type: ignore[arg-type]


def test_clean_description_strips_html_and_collapses_whitespace():
    raw = "Line one.<br>Line two.<b>Bold</b>   spaced."
    cleaned = bd._clean_description(raw)
    assert "<" not in cleaned and ">" not in cleaned
    assert "  " not in cleaned
    assert cleaned == "Line one. Line two. Bold spaced."


def test_clean_description_truncates_long_input_at_sentence_boundary():
    sentence = "This is a sentence with reasonable length. "
    raw = sentence * 100   # ~4300 chars, well over the cap
    cleaned = bd._clean_description(raw)
    assert len(cleaned) <= bd._MAX_DESCRIPTION_CHARS + 10  # +10 for "[…]" sentinel
    assert cleaned.endswith("[…]")


def test_clean_description_empty_returns_empty():
    assert bd._clean_description("") == ""
    assert bd._clean_description(None) == ""  # type: ignore[arg-type]


# ── Google Books ─────────────────────────────────────────────────────────────


def test_fetch_from_google_books_hit_returns_description():
    fixture = _load_fixture("google_books_hit.json")
    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen",
               return_value=_http_response(fixture)):
        result = bd.fetch_from_google_books("978-0-394-72024-1")
    assert result is not None
    assert result.source == "Google Books"
    assert "Robert Moses" in result.text
    # HTML tags must be stripped.
    assert "<br>" not in result.text
    # Categories are propagated and capped.
    assert "Biography & Autobiography / Historical" in result.categories
    assert result.isbn == "9780394720241"


def test_fetch_from_google_books_empty_returns_none():
    fixture = _load_fixture("google_books_empty.json")
    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen",
               return_value=_http_response(fixture)):
        result = bd.fetch_from_google_books("9780000000000")
    assert result is None


def test_fetch_from_google_books_missing_description_returns_none():
    """A volume with no description string should miss rather than return an
    empty description (so OL fallback gets a chance)."""
    payload = {"totalItems": 1, "items": [{"volumeInfo": {"title": "X"}}]}
    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen",
               return_value=_http_response(payload)):
        result = bd.fetch_from_google_books("9780000000000")
    assert result is None


def test_fetch_from_google_books_empty_isbn_returns_none():
    assert bd.fetch_from_google_books("") is None


# ── Open Library ─────────────────────────────────────────────────────────────


def test_fetch_from_open_library_uses_excerpts_when_no_description():
    fixture = _load_fixture("openlibrary_description.json")
    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen",
               return_value=_http_response(fixture)):
        result = bd.fetch_from_open_library("9780394720241")
    assert result is not None
    assert result.source == "Open Library"
    assert "Robert Moses" in result.text
    # Categories normalised across str and {"name": "..."} entries.
    assert "Politicians" in result.categories
    assert "Biography" in result.categories


def test_fetch_from_open_library_handles_typed_description():
    payload = {
        "ISBN:9780000000001": {
            "description": {"type": "/type/text", "value": "A typed-shape description."}
        }
    }
    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen",
               return_value=_http_response(payload)):
        result = bd.fetch_from_open_library("9780000000001")
    assert result is not None
    assert result.text == "A typed-shape description."


def test_fetch_from_open_library_no_description_returns_none():
    payload = {"ISBN:9780000000001": {"title": "X"}}
    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen",
               return_value=_http_response(payload)):
        result = bd.fetch_from_open_library("9780000000001")
    assert result is None


def test_fetch_from_open_library_empty_payload_returns_none():
    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen",
               return_value=_http_response({})):
        result = bd.fetch_from_open_library("9780000000001")
    assert result is None


# ── Cascade logic + graceful degradation ─────────────────────────────────────


def test_fetch_description_returns_google_when_present():
    google_fixture = _load_fixture("google_books_hit.json")
    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen",
               return_value=_http_response(google_fixture)) as mock_url:
        result = bd.fetch_description("9780394720241")
    assert result is not None
    assert result.source == "Google Books"
    # Only one HTTP call needed when Google Books hits.
    assert mock_url.call_count == 1


def test_fetch_description_falls_back_to_open_library_on_google_miss():
    empty = _load_fixture("google_books_empty.json")
    ol = _load_fixture("openlibrary_description.json")
    responses = [_http_response(empty), _http_response(ol)]
    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen",
               side_effect=responses) as mock_url:
        result = bd.fetch_description("9780394720241")
    assert result is not None
    assert result.source == "Open Library"
    assert mock_url.call_count == 2


def test_fetch_description_returns_none_when_both_miss():
    """Graceful degradation: both sources empty -> None, no exception."""
    empty_google = _load_fixture("google_books_empty.json")
    empty_ol = {}
    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen",
               side_effect=[_http_response(empty_google), _http_response(empty_ol)]):
        result = bd.fetch_description("9780000000001")
    assert result is None


def test_fetch_description_returns_none_on_persistent_network_error():
    """Graceful degradation: every retry of every source times out -> None."""
    def _raise(*args, **kwargs):
        raise TimeoutError("simulated timeout")
    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen",
               side_effect=_raise):
        result = bd.fetch_description("9780394720241", timeout=0.1, max_retries=1)
    assert result is None


def test_fetch_description_returns_none_on_4xx_response():
    """A 4xx response is a definitive miss (not retried) -> None."""
    err = urllib.error.HTTPError(
        url="x", code=404, msg="Not Found", hdrs=None, fp=io.BytesIO(b""),
    )
    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen",
               side_effect=err):
        result = bd.fetch_description("9780000000001", max_retries=1)
    assert result is None


def test_fetch_description_empty_isbn_short_circuits():
    """An empty ISBN should not make any HTTP calls."""
    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen") as mock_url:
        result = bd.fetch_description("")
    assert result is None
    assert mock_url.call_count == 0


# ── Batch ────────────────────────────────────────────────────────────────────


def test_fetch_descriptions_batch_returns_only_hits():
    google = _load_fixture("google_books_hit.json")
    empty = _load_fixture("google_books_empty.json")

    call_log: list[str] = []

    def _side_effect(req, *a, **kw):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        call_log.append(url)
        if "9780394720241" in url:
            return _http_response(google)
        return _http_response(empty)

    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen",
               side_effect=_side_effect):
        result = bd.fetch_descriptions_batch(
            {1: "9780394720241", 2: "9780000000000"},
            max_retries=1,
        )

    assert set(result.keys()) == {1}
    assert result[1].source == "Google Books"


def test_fetch_descriptions_batch_empty_input_returns_empty():
    assert bd.fetch_descriptions_batch({}) == {}


def test_fetch_descriptions_batch_skips_books_without_isbn():
    with patch("calibre_toolkit.services.book_description.urllib.request.urlopen") as mock_url:
        result = bd.fetch_descriptions_batch({1: "", 2: "  "})
    assert result == {}
    assert mock_url.call_count == 0
