"""
Pre-fetch publisher / community-sourced book descriptions for step 03.

Step 03 (LCC enrichment) sends title, authors, and ISBN to the AI. For
obscure books the AI was free to invent an `lcc_summary` from training
memory — sometimes confidently wrong. This module fetches a short
authoritative description from public sources before the AI call so the
prompt can instruct the model to summarise from the description rather
than from training data.

Source order (first hit wins):

  1. Google Books — `volumes?q=isbn:<isbn>[&key=...]`
     Returns `items[0].volumeInfo.description` plus `categories`.
     Google's anonymous quota is currently zero — every unauthenticated
     request returns HTTP 429. An API key is required for Google Books
     to participate at all. The key is read from the
     `GOOGLE_BOOKS_API_KEY` environment variable (preferred) or
     `description.google_books_api_key` in config.json. When no key is
     available, Google Books is skipped entirely so we don't waste
     network round trips.

  2. Open Library — `api/books?bibkeys=ISBN:<isbn>&jscmd=data&format=json`
     No key required; community-sourced descriptions and subjects.
     Used as the primary path when no Google Books key is available,
     and as fallback when Google Books has no description for an ISBN.

Both lookups are best-effort: any network failure, missing field, or
parse error returns None so the LCC step degrades cleanly to its
pre-prefetch behaviour. The HTTP discipline reuses the shared retry
helper, just like services/lc_catalog.py.

See ROADMAP.md item 11.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

from ..logging_config import get_logger
from ..retry import retry_with_backoff

_USER_AGENT = "calibre-lcc-toolkit/1.0 (personal library; +https://github.com/)"
_DEFAULT_TIMEOUT = 10.0
_DEFAULT_MAX_RETRIES = 3
_MAX_DESCRIPTION_CHARS = 1500  # Cap to keep prompt size predictable.
_MIN_DESCRIPTION_CHARS = 80    # Floor below which a "description" is almost
                               # always a MARC artifact (e.g. "Bibliography:
                               # p. [1173]-1177. Includes index.") rather
                               # than real description content.
_MAX_CATEGORIES = 6

_log = get_logger(__name__)


class _TransientHTTPError(Exception):
    """Internal sentinel — a network/HTTP error worth retrying."""


class _QuotaExceededError(Exception):
    """Internal sentinel — Google Books returned HTTP 429 (no quota).

    Not retried because the quota is per-day, not per-request. The caller
    catches this and disables Google Books for the rest of the session.
    """


@dataclass
class BookDescription:
    """A publisher / community-sourced description for a single ISBN."""
    text: str                     # Plain text, capped at _MAX_DESCRIPTION_CHARS.
    source: str                   # "Google Books" or "Open Library".
    categories: list[str]         # Subject categories from the source.
    isbn: str = ""                # The ISBN we used (for traceability).


# ── Google Books session state ───────────────────────────────────────────────
#
# Once the API returns 429 for an unauthenticated request (or for one with
# an invalid key), every subsequent call in the same process will return
# the same 429 — Google's quota is per-day. Caching that "disabled" state
# means a 50-book batch costs one wasted call rather than fifty.

_google_books_state_lock = threading.Lock()
_google_books_disabled: bool = False
_google_books_disabled_reason: str = ""


def _disable_google_books(reason: str) -> None:
    global _google_books_disabled, _google_books_disabled_reason
    with _google_books_state_lock:
        if not _google_books_disabled:
            _google_books_disabled = True
            _google_books_disabled_reason = reason
            _log.warning(
                "Google Books disabled for the rest of this session: %s. "
                "Open Library will be used for description lookups.",
                reason,
            )


def reset_google_books_state() -> None:
    """Test-only helper: re-enable Google Books between unit tests."""
    global _google_books_disabled, _google_books_disabled_reason
    with _google_books_state_lock:
        _google_books_disabled = False
        _google_books_disabled_reason = ""


def _google_books_is_disabled() -> bool:
    with _google_books_state_lock:
        return _google_books_disabled


# ── HTTP helper ──────────────────────────────────────────────────────────────


def _http_get_json(
    url: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[dict]:
    """Fetch a URL and parse JSON. Returns None on any non-retryable failure.

    Mirrors the LC/OL helper in services/lc_catalog.py — 5xx and connection
    errors retry with exponential backoff; 4xx and JSON parse errors return
    None immediately. HTTP 429 is raised as _QuotaExceededError without a
    retry so the caller can permanently disable the offending source for
    the session.
    """

    def _attempt() -> Optional[dict]:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                data = resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise _QuotaExceededError(f"HTTP 429 from {url}") from e
            if 500 <= e.code < 600:
                raise _TransientHTTPError(f"HTTP {e.code} from {url}") from e
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise _TransientHTTPError(f"network error from {url}: {e}") from e
        try:
            return json.loads(data)
        except (json.JSONDecodeError, ValueError):
            return None

    try:
        return retry_with_backoff(
            _attempt,
            max_retries=max_retries,
            retry_on=(_TransientHTTPError,),
            description=f"book-description HTTP GET {urllib.parse.urlparse(url).netloc}",
        )
    except _TransientHTTPError:
        return None


# ── ISBN normalisation ────────────────────────────────────────────────────────


def _normalise_isbn(isbn: str) -> str:
    if not isbn:
        return ""
    return re.sub(r"[\s\-]", "", isbn.strip())


# ── Text cleaning ─────────────────────────────────────────────────────────────


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _clean_description(raw: str) -> str:
    """Strip HTML tags, collapse whitespace, cap length, and quality-gate.

    Google Books descriptions occasionally contain inline `<br>`, `<b>`,
    or `<i>` markup. We feed plain text to the AI so the prompt stays
    deterministic and predictable.

    Quality gate: anything under `_MIN_DESCRIPTION_CHARS` after cleanup
    is returned as an empty string. Very short "descriptions" on the
    public catalog APIs are almost always MARC artifacts ("Includes
    bibliographical references and index.") rather than real prose, and
    summarising from them would be worse than falling back to AI
    training data.
    """
    if not raw:
        return ""
    no_html = _HTML_TAG_RE.sub(" ", raw)
    collapsed = _WHITESPACE_RE.sub(" ", no_html).strip()
    if len(collapsed) < _MIN_DESCRIPTION_CHARS:
        return ""
    if len(collapsed) > _MAX_DESCRIPTION_CHARS:
        # Truncate at the last sentence boundary inside the cap so we never
        # split mid-word.
        truncated = collapsed[:_MAX_DESCRIPTION_CHARS]
        last_period = truncated.rfind(". ")
        if last_period >= _MAX_DESCRIPTION_CHARS // 2:
            truncated = truncated[: last_period + 1]
        collapsed = truncated.rstrip() + " […]"
    return collapsed


# ── Google Books ──────────────────────────────────────────────────────────────


def _resolve_google_books_api_key(explicit: Optional[str] = None) -> str:
    """Pick the Google Books API key from (in order): explicit argument,
    `GOOGLE_BOOKS_API_KEY` env var. Empty string when none is set."""
    if explicit:
        return explicit.strip()
    return (os.environ.get("GOOGLE_BOOKS_API_KEY") or "").strip()


def fetch_from_google_books(
    isbn: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    api_key: Optional[str] = None,
) -> Optional[BookDescription]:
    """Look up a description on Google Books by ISBN.

    Google's public quota for anonymous requests is currently zero, so a
    key is required. When no key is available — or once we've hit 429
    earlier in this session — this function short-circuits to None
    without making an HTTP call.
    """
    cleaned = _normalise_isbn(isbn)
    if not cleaned:
        return None
    if _google_books_is_disabled():
        return None
    key = _resolve_google_books_api_key(api_key)
    if not key:
        # First call only — disable for the rest of the session so we don't
        # spam this warning. The caller (modules/lcc.py) also surfaces a
        # one-line note when the key is absent.
        _disable_google_books(
            "no GOOGLE_BOOKS_API_KEY set "
            "(env var or description.google_books_api_key in config.json)"
        )
        return None
    params = urllib.parse.urlencode({"q": f"isbn:{cleaned}", "key": key})
    url = f"https://www.googleapis.com/books/v1/volumes?{params}"
    try:
        data = _http_get_json(url, timeout=timeout, max_retries=max_retries)
    except _QuotaExceededError as e:
        _disable_google_books(f"HTTP 429 from API ({e}); quota exhausted or key invalid")
        return None
    if not data:
        _log.debug("Google Books: no response or network failure for ISBN %s", cleaned)
        return None
    items = data.get("items") or []
    if not items:
        _log.debug("Google Books: ISBN %s — 0 items in response", cleaned)
        return None
    vol = (items[0] or {}).get("volumeInfo") or {}
    raw = vol.get("description") or ""
    text = _clean_description(raw if isinstance(raw, str) else "")
    if not text:
        _log.debug("Google Books: ISBN %s — item found but no description field", cleaned)
        return None
    categories = [c for c in (vol.get("categories") or []) if isinstance(c, str)]
    _log.debug(
        "Google Books: ISBN %s — hit (%d chars, %d categories)",
        cleaned, len(text), len(categories),
    )
    return BookDescription(
        text=text,
        source="Google Books",
        categories=categories[:_MAX_CATEGORIES],
        isbn=cleaned,
    )


# ── Open Library ──────────────────────────────────────────────────────────────


def _ol_extract_description(record: dict) -> str:
    """OL returns description in two shapes depending on source: a plain
    string, or {"type": "/type/text", "value": "..."}. Excerpts are
    accepted as a fallback. `notes` is intentionally NOT consulted — on
    OL it almost always contains MARC cataloging boilerplate (e.g.
    "Bibliography: p. [1173]-1177. Includes index.") that would mislead
    the AI rather than help it.
    """
    raw = record.get("description")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        v = raw.get("value")
        if isinstance(v, str):
            return v
    # Excerpts are usually a short snippet of the book itself; safer than
    # MARC notes but should still be quality-gated by the length floor in
    # the caller.
    excerpts = record.get("excerpts") or []
    if isinstance(excerpts, list) and excerpts:
        first = excerpts[0]
        if isinstance(first, dict):
            text = first.get("text") or first.get("comment") or ""
            if isinstance(text, str):
                return text
    return ""


def _ol_extract_categories(record: dict) -> list[str]:
    """OL's subjects list can be plain strings or {"name": "..."} dicts."""
    raw = record.get("subjects") or []
    out: list[str] = []
    for entry in raw:
        if isinstance(entry, str):
            out.append(entry)
        elif isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str):
                out.append(name)
    return out


def fetch_from_open_library(
    isbn: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[BookDescription]:
    """Look up a description on Open Library by ISBN."""
    cleaned = _normalise_isbn(isbn)
    if not cleaned:
        return None
    params = urllib.parse.urlencode({
        "bibkeys": f"ISBN:{cleaned}",
        "jscmd": "data",
        "format": "json",
    })
    url = f"https://openlibrary.org/api/books?{params}"
    data = _http_get_json(url, timeout=timeout, max_retries=max_retries)
    if not data:
        _log.debug("Open Library: no response or network failure for ISBN %s", cleaned)
        return None
    record = data.get(f"ISBN:{cleaned}") or {}
    if not record:
        _log.debug("Open Library: ISBN %s — no record in response", cleaned)
        return None
    text = _clean_description(_ol_extract_description(record))
    if not text:
        _log.debug(
            "Open Library: ISBN %s — record found but no description / excerpts / notes",
            cleaned,
        )
        return None
    categories = _ol_extract_categories(record)
    _log.debug(
        "Open Library: ISBN %s — hit (%d chars, %d subjects)",
        cleaned, len(text), len(categories),
    )
    return BookDescription(
        text=text,
        source="Open Library",
        categories=categories[:_MAX_CATEGORIES],
        isbn=cleaned,
    )


# ── Public lookups ────────────────────────────────────────────────────────────


def fetch_description(
    isbn: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    google_books_api_key: Optional[str] = None,
) -> Optional[BookDescription]:
    """Try Google Books, then Open Library. Return None if both miss.

    Graceful degradation: any network failure surfaces as None. The caller
    is responsible for treating None as "no description available, fall
    back to AI training data" — there is no exception path here.
    """
    cleaned = _normalise_isbn(isbn)
    if not cleaned:
        return None
    try:
        google = fetch_from_google_books(
            cleaned, timeout=timeout, max_retries=max_retries,
            api_key=google_books_api_key,
        )
        if google:
            return google
    except Exception as e:
        _log.debug("Google Books lookup raised %s for ISBN %s; falling through", e, cleaned)
    try:
        ol = fetch_from_open_library(cleaned, timeout=timeout, max_retries=max_retries)
        if ol:
            return ol
    except Exception as e:
        _log.debug("Open Library lookup raised %s for ISBN %s; falling through", e, cleaned)
    return None


def fetch_descriptions_batch(
    isbn_by_book_id: dict[int, str],
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    max_workers: int = 8,
    google_books_api_key: Optional[str] = None,
) -> dict[int, BookDescription]:
    """Fetch descriptions for many books in parallel.

    Books with no ISBN, or where every source misses, are simply absent
    from the returned dict. The caller can treat the dict like a
    best-effort cache: present means "use this description"; absent means
    "no description available, let the AI use training data".
    """
    if not isbn_by_book_id:
        return {}
    out: dict[int, BookDescription] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(
                fetch_description, isbn, timeout, max_retries, google_books_api_key,
            ): bid
            for bid, isbn in isbn_by_book_id.items()
            if _normalise_isbn(isbn)
        }
        for fut in as_completed(futures):
            bid = futures[fut]
            try:
                result = fut.result()
            except Exception as e:
                _log.debug("description fetch raised for book %s: %s", bid, e)
                result = None
            if result is not None:
                out[bid] = result
    return out
