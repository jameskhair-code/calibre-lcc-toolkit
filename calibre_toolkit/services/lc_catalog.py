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
      All editions of a work. Each edition carries its own ISBN(s).
      The cascade enumerates sibling ISBNs from these entries and
      issues a single batched bibkeys lookup across them. Catches
      UK / international ISBNs whose specific edition lacks LC data
      but whose US sibling does.

All functions are best-effort: any network failure, missing field, or
parse error returns None so the caller can fall through to AI
classification.

The ISBN → work-key result is persisted across runs at
~/.calibre-toolkit/ol-workkey-cache.json (90-day TTL, configurable via
the CALIBRE_TOOLKIT_OL_WORKKEY_CACHE env override). Subsequent runs
against the same library skip the /isbn/{isbn}.json lookup entirely
for ISBNs already resolved (positive or negative). The in-process
work-editions cache (keyed by work_key) is separate and not persisted.
"""

from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
    treat_4xx_as_empty: bool = False,
) -> Optional[dict]:
    """Fetch a URL and parse JSON. Returns None on any non-retryable failure.

    Retries 5xx responses, timeouts, and connection errors with exponential
    backoff. 4xx responses and JSON parse errors are returned as None
    immediately — they will not improve on retry.

    When `treat_4xx_as_empty=True`, definitive 4xx responses (e.g. OL's
    404 for an unknown ISBN) return `{}` instead of None so the caller
    can distinguish "OL has no record" from "transient HTTP failure" —
    used by the persistent work-key cache to know when a negative
    result is safe to cache.
    """

    def _attempt() -> Optional[dict]:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    return {} if treat_4xx_as_empty else None
                data = resp.read()
        except urllib.error.HTTPError as e:
            if 500 <= e.code < 600:
                raise _TransientHTTPError(f"HTTP {e.code} from {url}") from e
            return {} if treat_4xx_as_empty else None
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


def _lookup_isbns_openlibrary_batch(
    isbns: list[str],
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> dict[str, Optional[CatalogHit]]:
    """Resolve a batch of ISBNs to LC call numbers in one OL request.

    Output is keyed by each input string. Duplicates and blank inputs
    collapse to one HTTP request; each input key still appears in the
    output mapping with a CatalogHit or None.
    """
    out: dict[str, Optional[CatalogHit]] = {raw: None for raw in isbns if raw is not None}
    raw_to_cleaned: dict[str, str] = {}
    cleaned_seen: list[str] = []
    for raw in isbns:
        if raw is None:
            continue
        cleaned = re.sub(r"[\s\-]", "", raw.strip())
        if not cleaned:
            continue
        raw_to_cleaned[raw] = cleaned
        if cleaned not in cleaned_seen:
            cleaned_seen.append(cleaned)
    if not cleaned_seen:
        return out
    params = urllib.parse.urlencode({
        "bibkeys": ",".join(f"ISBN:{c}" for c in cleaned_seen),
        "jscmd": "data",
        "format": "json",
    })
    url = f"https://openlibrary.org/api/books?{params}"
    data = _http_get_json(url, timeout=timeout, max_retries=max_retries)
    if not data:
        return out
    hit_by_cleaned: dict[str, CatalogHit] = {}
    for cleaned in cleaned_seen:
        record = data.get(f"ISBN:{cleaned}") or {}
        lc_classes = (record.get("classifications") or {}).get("lc_classifications") or []
        call = _pick_lcc_call_number(lc_classes)
        if call:
            hit_by_cleaned[cleaned] = CatalogHit(
                call_number=call,
                source=f"Open Library (ISBN {cleaned})",
            )
    for raw, cleaned in raw_to_cleaned.items():
        out[raw] = hit_by_cleaned.get(cleaned)
    return out


def lookup_by_isbn_openlibrary(
    isbn: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[CatalogHit]:
    """Resolve an ISBN to an LC call number via Open Library."""
    if not isbn:
        return None
    results = _lookup_isbns_openlibrary_batch(
        [isbn], timeout=timeout, max_retries=max_retries,
    )
    return results.get(isbn)


# ── Open Library edition cascade ─────────────────────────────────────────────
#
# Many UK / Commonwealth / international ISBNs lack LC classifications on
# their own OL record but have US sibling editions of the same work that
# DO carry the classifications. The cascade walks OL's edition graph to
# discover those siblings and re-runs the bibkeys lookup against each.
#
# Cap raised to 10 (from 3) after the probe in
# scripts/probe_lcc_sources.py demonstrated that the deeper walk lifts
# hit rate from 27% → 76% on books with ISBNs. With v1.7's batched
# bibkeys lookup the cap is also a safety belt on URL length and OL
# response size — 10 ISBN-13 fits comfortably in one request — and the
# cache below still stops repeat work on shared works.

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


# ── Persistent ISBN → work-key cache (v1.7 item 4) ───────────────────────────
#
# Resolving "this ISBN belongs to OL work XYZ" is stable across runs — the OL
# /isbn/{isbn}.json endpoint returns the same work key today and tomorrow.
# Pre-v1.7-item-4 the resolution had no cache at all; the v1.7 item 2
# measurement clocked it at ~3.5–4 s per call and 3.5 s × every cascading book
# in every fresh run. Persist the result to a JSON file under
# ~/.calibre-toolkit/ so subsequent runs against the same library skip the
# lookups they already did.
#
# Both outcomes are cached:
#   - positive — OL returned a work key
#   - negative — OL responded but had no /works/ entry for this ISBN
# Negative caching matters because the cascade always tries the work-key
# resolve, even if the ISBN has been confirmed unresolvable in a prior run.
#
# HTTP failures (timeouts, transient 5xx after retry exhaustion) are NOT
# cached — they may improve on the next run.

_WORKKEY_CACHE_ENV = "CALIBRE_TOOLKIT_OL_WORKKEY_CACHE"
_DEFAULT_WORKKEY_CACHE_PATH = Path.home() / ".calibre-toolkit" / "ol-workkey-cache.json"
_WORKKEY_CACHE_TTL_DAYS = 90
_WORKKEY_CACHE_SCHEMA_VERSION = 1

# In-memory mirror of the on-disk cache. None means "not yet loaded from disk."
_workkey_cache_data: Optional[dict[str, dict]] = None
_workkey_cache_lock = threading.Lock()


def _workkey_cache_path() -> Path:
    override = os.environ.get(_WORKKEY_CACHE_ENV)
    return Path(override).expanduser() if override else _DEFAULT_WORKKEY_CACHE_PATH


def _load_workkey_cache() -> dict[str, dict]:
    """Load (or initialise) the in-memory cache from disk. Caller must hold
    `_workkey_cache_lock`. Missing or corrupt files return an empty cache —
    a parse error must not break catalog lookups."""
    global _workkey_cache_data
    if _workkey_cache_data is not None:
        return _workkey_cache_data
    path = _workkey_cache_path()
    if not path.exists():
        _workkey_cache_data = {}
        return _workkey_cache_data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as e:
        _log.warning(
            "OL work-key cache at %s is unreadable (%s); starting fresh", path, e,
        )
        _workkey_cache_data = {}
        return _workkey_cache_data
    if not isinstance(raw, dict) or raw.get("version") != _WORKKEY_CACHE_SCHEMA_VERSION:
        _log.warning(
            "OL work-key cache at %s has unexpected schema; starting fresh", path,
        )
        _workkey_cache_data = {}
        return _workkey_cache_data
    entries = raw.get("entries") or {}
    if not isinstance(entries, dict):
        _workkey_cache_data = {}
        return _workkey_cache_data
    _workkey_cache_data = entries
    return _workkey_cache_data


def _save_workkey_cache_locked() -> None:
    """Atomically dump the in-memory cache to disk. Caller must hold
    `_workkey_cache_lock`. Failures are logged and swallowed."""
    path = _workkey_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        payload = {
            "version": _WORKKEY_CACHE_SCHEMA_VERSION,
            "entries": _workkey_cache_data or {},
        }
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        _log.warning("OL work-key cache write to %s failed: %s", path, e)


def _workkey_cache_lookup(cleaned_isbn: str) -> tuple[bool, Optional[str]]:
    """Return (hit, work_key_or_None).

    hit=False    — not cached (or cached but past TTL); caller should HTTP.
    hit=True, work_key=str   — positive cached result.
    hit=True, work_key=None  — negative cached result (OL has no work for this ISBN).
    """
    with _workkey_cache_lock:
        cache = _load_workkey_cache()
        entry = cache.get(cleaned_isbn)
        if not entry:
            return False, None
        fetched = entry.get("fetched_at")
        try:
            fetched_dt = datetime.fromisoformat(fetched)
        except (TypeError, ValueError):
            return False, None
        if fetched_dt.tzinfo is None:
            fetched_dt = fetched_dt.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - fetched_dt > timedelta(days=_WORKKEY_CACHE_TTL_DAYS):
            return False, None
        work_key = entry.get("work_key")
        if work_key is not None and not isinstance(work_key, str):
            return False, None
        return True, work_key


def _workkey_cache_store(cleaned_isbn: str, work_key: Optional[str]) -> None:
    """Persist a positive or negative cache entry."""
    with _workkey_cache_lock:
        cache = _load_workkey_cache()
        cache[cleaned_isbn] = {
            "work_key": work_key,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        _save_workkey_cache_locked()


def reset_workkey_cache() -> None:
    """Test-only helper: drop the in-memory cache and delete the cache file
    (if it exists at the currently-configured path)."""
    global _workkey_cache_data
    with _workkey_cache_lock:
        _workkey_cache_data = None
        path = _workkey_cache_path()
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass


def _ol_work_key_for_isbn(
    isbn: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[str]:
    """Resolve an ISBN to its OL work key (e.g. '/works/OL12345W').

    Checks the persistent ISBN → work-key cache first. On miss (cold or stale),
    fetches /isbn/{isbn}.json and persists the result. HTTP failures are not
    cached.
    """
    if not isbn:
        return None
    cleaned = re.sub(r"[\s\-]", "", isbn.strip())
    if not cleaned:
        return None
    hit, cached = _workkey_cache_lookup(cleaned)
    if hit:
        return cached
    url = f"https://openlibrary.org/isbn/{urllib.parse.quote(cleaned)}.json"
    data = _http_get_json(
        url, timeout=timeout, max_retries=max_retries,
        treat_4xx_as_empty=True,
    )
    if data is None:
        # Transient (network/5xx after retries) — don't poison the cache.
        return None
    # data is {} for OL 404 (definite negative) or a parsed dict.
    works = data.get("works") or []
    found: Optional[str] = None
    for entry in works:
        key = (entry or {}).get("key")
        if isinstance(key, str) and key.startswith("/works/"):
            found = key
            break
    _workkey_cache_store(cleaned, found)
    return found


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
    missed. Resolves the OL work, fetches its editions, then issues one
    batched `/api/books?bibkeys=...` lookup across every sibling ISBN
    at once. Returns the first sibling hit in cascade preference order,
    or None.
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
        "Edition cascade: batching %d sibling ISBN(s) for work %s",
        len(siblings), work_key,
    )
    results = _lookup_isbns_openlibrary_batch(
        siblings, timeout=timeout, max_retries=max_retries,
    )
    for sib in siblings:
        hit = results.get(sib)
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
