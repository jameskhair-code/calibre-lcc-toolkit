"""
Pre-fetch publisher / community-sourced book descriptions for step 03.

Step 03 (LCC enrichment) sends title, authors, and ISBN to the AI. For
obscure books the AI was free to invent an `lcc_summary` from training
memory — sometimes confidently wrong. This module fetches a short
authoritative description from public sources before the AI call so the
prompt can instruct the model to summarise from the description rather
than from training data.

Source order (first hit wins):

  1. Google Books — `volumes?q=isbn:<isbn>`
     Returns `items[0].volumeInfo.description` plus `categories`. No API
     key needed for basic ISBN lookups.

  2. Open Library — `api/books?bibkeys=ISBN:<isbn>&jscmd=data&format=json`
     Returns a `description` (sometimes a string, sometimes
     `{"value": "..."}`) and `subjects`. Used when Google Books has no
     description for the ISBN.

Both lookups are best-effort: any network failure, missing field, or
parse error returns None so the LCC step degrades cleanly to its
pre-prefetch behaviour. The HTTP discipline reuses the shared retry
helper, just like services/lc_catalog.py.

See ROADMAP.md item 11.
"""

from __future__ import annotations

import json
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
_MAX_CATEGORIES = 6

_log = get_logger(__name__)


class _TransientHTTPError(Exception):
    """Internal sentinel — a network/HTTP error worth retrying."""


@dataclass
class BookDescription:
    """A publisher / community-sourced description for a single ISBN."""
    text: str                     # Plain text, capped at _MAX_DESCRIPTION_CHARS.
    source: str                   # "Google Books" or "Open Library".
    categories: list[str]         # Subject categories from the source.
    isbn: str = ""                # The ISBN we used (for traceability).


# ── HTTP helper ──────────────────────────────────────────────────────────────


def _http_get_json(
    url: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[dict]:
    """Fetch a URL and parse JSON. Returns None on any non-retryable failure.

    Mirrors the LC/OL helper in services/lc_catalog.py — 5xx and connection
    errors retry with exponential backoff; 4xx and JSON parse errors return
    None immediately.
    """

    def _attempt() -> Optional[dict]:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                data = resp.read()
        except urllib.error.HTTPError as e:
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
    """Strip HTML tags, collapse whitespace, and cap length.

    Google Books descriptions occasionally contain inline `<br>`, `<b>`,
    or `<i>` markup. We feed plain text to the AI so the prompt stays
    deterministic and predictable.
    """
    if not raw:
        return ""
    no_html = _HTML_TAG_RE.sub(" ", raw)
    collapsed = _WHITESPACE_RE.sub(" ", no_html).strip()
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


def fetch_from_google_books(
    isbn: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[BookDescription]:
    """Look up a description on Google Books by ISBN."""
    cleaned = _normalise_isbn(isbn)
    if not cleaned:
        return None
    params = urllib.parse.urlencode({"q": f"isbn:{cleaned}"})
    url = f"https://www.googleapis.com/books/v1/volumes?{params}"
    data = _http_get_json(url, timeout=timeout, max_retries=max_retries)
    if not data:
        return None
    items = data.get("items") or []
    if not items:
        return None
    vol = (items[0] or {}).get("volumeInfo") or {}
    raw = vol.get("description") or ""
    text = _clean_description(raw if isinstance(raw, str) else "")
    if not text:
        return None
    categories = [c for c in (vol.get("categories") or []) if isinstance(c, str)]
    return BookDescription(
        text=text,
        source="Google Books",
        categories=categories[:_MAX_CATEGORIES],
        isbn=cleaned,
    )


# ── Open Library ──────────────────────────────────────────────────────────────


def _ol_extract_description(record: dict) -> str:
    """OL returns description in two shapes depending on source: a plain
    string, or {"type": "/type/text", "value": "..."}. Handle both."""
    raw = record.get("description")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        v = raw.get("value")
        if isinstance(v, str):
            return v
    # The `/api/books?jscmd=data` shape uses "excerpts" / "notes" / "subtitle"
    # rather than `description`. Fall back through them in order.
    excerpts = record.get("excerpts") or []
    if isinstance(excerpts, list) and excerpts:
        first = excerpts[0]
        if isinstance(first, dict):
            text = first.get("text") or first.get("comment") or ""
            if isinstance(text, str):
                return text
    notes = record.get("notes")
    if isinstance(notes, str):
        return notes
    if isinstance(notes, dict):
        v = notes.get("value")
        if isinstance(v, str):
            return v
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
        return None
    record = data.get(f"ISBN:{cleaned}") or {}
    text = _clean_description(_ol_extract_description(record))
    if not text:
        return None
    categories = _ol_extract_categories(record)
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
        google = fetch_from_google_books(cleaned, timeout=timeout, max_retries=max_retries)
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
            ex.submit(fetch_description, isbn, timeout, max_retries): bid
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
