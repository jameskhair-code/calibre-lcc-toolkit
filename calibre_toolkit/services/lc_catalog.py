"""
LC call-number lookups, sourced exclusively from Open Library.

Historical note
---------------
This module used to query the Library of Congress catalog directly
(www.loc.gov/books and lx2.loc.gov/sru). LC put their public APIs
behind Cloudflare's JavaScript challenge during the v1.3 cycle, which
`urllib` cannot solve. We then ran the alternative-source probe
(scripts/probe_lcc_sources.py) and found that **deepening Open
Library's edition cascade produces real catalog-sourced LC call
numbers for ~76% of books with ISBNs** — without ever touching LC.

So the LC paths were removed entirely. The module still produces LC
call numbers; it just sources them through Open Library's data
graph instead. The investigation that led here is in
docs/LC-Cloudflare-Investigation.md.

Public endpoints used (no API key needed):

  • https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&jscmd=data&format=json
      OL's bibliographic record for one ISBN. The
      `classifications.lc_classifications` list carries LCC strings
      drawn from member-library cataloging.

  • https://openlibrary.org/isbn/{isbn}.json
      Single OL edition record. Returns `works: [{key: "/works/OLxxxW"}]`
      pointing at the canonical work — the bridge into the edition
      cascade.

  • https://openlibrary.org/works/{wid}/editions.json
      All editions of a work. Each edition carries its own ISBN(s) and
      may have its own classifications block. The cascade walks
      sibling editions and re-runs the bibkeys lookup against each.
      Catches UK / international ISBNs whose specific edition lacks
      LC data but whose US sibling does.

All functions are best-effort: any network failure, missing field, or
parse error returns None so the caller can fall through to AI
classification.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from ..logging_config import get_logger
from ..retry import retry_with_backoff

_USER_AGENT = "calibre-lcc-toolkit/1.0 (personal library; +https://github.com/)"
_DEFAULT_TIMEOUT = 10.0
_DEFAULT_MAX_RETRIES = 3

_log = get_logger(__name__)


class _TransientHTTPError(Exception):
    """Internal sentinel — a network/HTTP error worth retrying."""


@dataclass
class CatalogHit:
    """A confirmed LC call number lookup result."""
    call_number: str
    source: str             # short label: "Open Library (ISBN ...)" etc.


# ── HTTP helper ───────────────────────────────────────────────────────────────


def _http_get_json(
    url: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[dict]:
    """Fetch a URL and parse JSON. Returns None on any non-retryable failure.

    Retries 5xx responses, timeouts, and connection errors with exponential
    backoff. 4xx responses and JSON parse errors are returned as None
    immediately — they will not improve on retry.
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
            description=f"OL HTTP GET {urllib.parse.urlparse(url).netloc}",
        )
    except _TransientHTTPError:
        return None


# ── Field extraction ──────────────────────────────────────────────────────────


_LCC_CALLNUMBER_RE = re.compile(r"^[A-Z]{1,3}[0-9]")  # quick sanity: LC class numbers start like this


def _pick_lcc_call_number(call_numbers: list) -> Optional[str]:
    """From a list of catalog call-number strings, return the first that looks
    like an LCC class number (starts with 1–3 capital letters then a digit).

    Records can also contain Dewey, MARC holdings notes, etc. — those are
    skipped.
    """
    if not call_numbers:
        return None
    for entry in call_numbers:
        if not isinstance(entry, str):
            continue
        candidate = entry.strip()
        if not candidate:
            continue
        # Some records prefix with brackets or notes; strip leading non-letters.
        m = re.search(r"\b[A-Z]{1,3}[0-9][0-9A-Z. ]*", candidate)
        if m:
            return m.group(0).strip()
    return None


# ── Open Library direct ISBN lookup ──────────────────────────────────────────


def lookup_by_isbn_openlibrary(
    isbn: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[CatalogHit]:
    """Resolve an ISBN to an LC call number via Open Library."""
    if not isbn:
        return None
    cleaned = re.sub(r"[\s\-]", "", isbn.strip())
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
    lc_classes = (record.get("classifications") or {}).get("lc_classifications") or []
    call = _pick_lcc_call_number(lc_classes)
    if not call:
        return None
    return CatalogHit(
        call_number=call,
        source=f"Open Library (ISBN {cleaned})",
    )


# ── Open Library edition cascade ─────────────────────────────────────────────
#
# Many UK / Commonwealth / international ISBNs lack LC classifications on
# their own OL record but have US sibling editions of the same work that
# DO carry the classifications. The cascade walks OL's edition graph to
# discover those siblings and re-runs the bibkeys lookup against each.
#
# Cap raised to 10 (from 3) after the probe in
# scripts/probe_lcc_sources.py demonstrated that the deeper walk lifts
# hit rate from 27% → 76% on books with ISBNs. The cap is conservative
# enough that worst-case time per book stays bounded; the cache below
# stops repeat work on shared works.

_EDITION_CASCADE_MAX_ISBNS = 10


# Module-level cache for OL work editions, keyed by work_key. Several
# books in a series share a work; without this cache each book would
# refetch /works/{wid}/editions.json. Per-process — survives the duration
# of one CLI invocation and is discarded after.

_work_editions_cache: dict[str, list[dict]] = {}
_work_editions_lock = threading.Lock()


def _get_work_editions_entries(
    work_key: str,
    timeout: float,
    max_retries: int,
) -> list[dict]:
    """Cached fetch of an OL work's editions list. Returns the raw entries
    array (the caller filters from it). Empty list on miss/failure."""
    with _work_editions_lock:
        cached = _work_editions_cache.get(work_key)
        if cached is not None:
            return cached
    url = f"https://openlibrary.org{work_key}/editions.json"
    data = _http_get_json(url, timeout=timeout, max_retries=max_retries)
    entries = (data or {}).get("entries") or []
    with _work_editions_lock:
        _work_editions_cache[work_key] = entries
    return entries


def reset_work_editions_cache() -> None:
    """Test-only helper: drop the work-editions cache between unit tests."""
    with _work_editions_lock:
        _work_editions_cache.clear()


def _ol_work_key_for_isbn(
    isbn: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[str]:
    """Resolve an ISBN to its OL work key (e.g. '/works/OL12345W')."""
    if not isbn:
        return None
    cleaned = re.sub(r"[\s\-]", "", isbn.strip())
    if not cleaned:
        return None
    url = f"https://openlibrary.org/isbn/{urllib.parse.quote(cleaned)}.json"
    data = _http_get_json(url, timeout=timeout, max_retries=max_retries)
    if not data:
        return None
    works = data.get("works") or []
    for entry in works:
        key = (entry or {}).get("key")
        if isinstance(key, str) and key.startswith("/works/"):
            return key
    return None


def _ol_sibling_isbns_for_work(
    work_key: str,
    excluded_isbn: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    max_isbns: int = _EDITION_CASCADE_MAX_ISBNS,
) -> list[str]:
    """Return a bounded list of other ISBNs that belong to the same work.

    English-language editions are preferred (when the language field is
    present); ISBN-13 are preferred over ISBN-10 within each edition.
    """
    if not work_key or not work_key.startswith("/works/"):
        return []
    entries = _get_work_editions_entries(work_key, timeout, max_retries)
    if not entries:
        return []
    excluded = re.sub(r"[\s\-]", "", (excluded_isbn or "").strip())

    english_isbns: list[str] = []
    other_isbns: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        is_english = False
        for lang in (entry.get("languages") or []):
            if isinstance(lang, dict) and lang.get("key") in ("/languages/eng",):
                is_english = True
                break
        # Prefer ISBN-13 first within each edition.
        for field in ("isbn_13", "isbn_10"):
            for raw in (entry.get(field) or []):
                if not isinstance(raw, str):
                    continue
                normalised = re.sub(r"[\s\-]", "", raw.strip())
                if not normalised or normalised == excluded:
                    continue
                bucket = english_isbns if is_english else other_isbns
                if normalised not in bucket:
                    bucket.append(normalised)

    out: list[str] = []
    for src in (english_isbns, other_isbns):
        for isbn in src:
            if isbn in out:
                continue
            out.append(isbn)
            if len(out) >= max_isbns:
                return out
    return out


def lookup_by_isbn_with_edition_cascade(
    isbn: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[CatalogHit]:
    """Walk OL's work / editions graph to find a sibling ISBN whose OL
    record carries an LC classification.

    Called only after the direct OL ISBN lookup for `isbn` has already
    missed. Resolves the OL work, fetches its editions, and re-runs
    `lookup_by_isbn_openlibrary` against each sibling ISBN. Returns the
    first hit (with a source string that records the cascade), or None.
    """
    if not isbn:
        return None
    work_key = _ol_work_key_for_isbn(isbn, timeout=timeout, max_retries=max_retries)
    if not work_key:
        _log.debug("Edition cascade: ISBN %s has no OL work key", isbn)
        return None
    siblings = _ol_sibling_isbns_for_work(
        work_key, excluded_isbn=isbn,
        timeout=timeout, max_retries=max_retries,
    )
    if not siblings:
        _log.debug(
            "Edition cascade: work %s has no sibling ISBNs to try", work_key,
        )
        return None
    _log.debug(
        "Edition cascade: trying %d sibling ISBN(s) for work %s",
        len(siblings), work_key,
    )
    for sib in siblings:
        hit = lookup_by_isbn_openlibrary(sib, timeout=timeout, max_retries=max_retries)
        if hit:
            return CatalogHit(
                call_number=hit.call_number,
                source=(
                    f"Open Library via edition cascade "
                    f"(seed ISBN {isbn}, matched sibling {sib})"
                ),
            )
    return None


# ── Public orchestration ─────────────────────────────────────────────────────


def lookup_book(
    identifiers: dict,
    title: str = "",
    author: str = "",
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[CatalogHit]:
    """Resolve a book to an LC call number via Open Library.

    Order (each step runs only if the previous missed):
      1. OL direct ISBN — the seed ISBN's own OL record.
      2. OL edition cascade — walk the work graph to sibling ISBNs and
         retry, catching UK/Commonwealth ISBNs whose US sibling is the
         one with classifications.

    `title` and `author` are accepted for signature stability with the
    pre-v1.3 cascade but not used today — when both ISBN paths miss
    we have no fallback that doesn't touch LC. The AI layer covers it.

    `identifiers` is the {type: value} dict from db.get_identifiers().
    """
    if not identifiers:
        return None

    isbn_values: list[str] = []
    for key in ("isbn", "isbn13", "isbn10", "ISBN"):
        v = identifiers.get(key)
        if v and v not in isbn_values:
            isbn_values.append(v)

    # 1. Direct OL ISBN lookup.
    for isbn in isbn_values:
        hit = lookup_by_isbn_openlibrary(
            isbn, timeout=timeout, max_retries=max_retries,
        )
        if hit:
            return hit

    # 2. OL edition cascade — sibling ISBNs of the same work.
    for isbn in isbn_values:
        hit = lookup_by_isbn_with_edition_cascade(
            isbn, timeout=timeout, max_retries=max_retries,
        )
        if hit:
            return hit

    return None
