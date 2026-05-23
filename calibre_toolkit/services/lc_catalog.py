"""
Library of Congress catalog lookups, with Open Library fallback.

Public endpoints used (no API key needed):

  • https://www.loc.gov/item/{lccn}/?fo=json
      Direct fetch of a single bibliographic record by LCCN.
      Response includes `item.call_number` as a list of strings.

  • https://www.loc.gov/books/?q={isbn}&fo=json&c=1
      ISBN-based search of the LC books catalog. First result's
      `call_number` field carries the canonical LC class number.

  • https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&jscmd=data&format=json
      Open Library fallback when LC misses (e.g. recent publications not
      yet catalogued). Response's `classifications.lc_classifications` is
      a list of LCC strings. Confidence: medium.

The functions here are best-effort: any network failure, missing field,
or parse error returns None so the caller can fall through to AI
classification.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

_USER_AGENT = "calibre-lcc-toolkit/1.0 (personal library; +https://github.com/)"
_DEFAULT_TIMEOUT = 10.0


@dataclass
class CatalogHit:
    """A confirmed LC call number lookup result."""
    call_number: str
    source: str             # short label: "LC catalog (LCCN 2024012345)" etc.
    raw_lccn: str = ""      # the LCCN we used, if any (for traceability)


# ── HTTP helper ───────────────────────────────────────────────────────────────


def _http_get_json(url: str, timeout: float = _DEFAULT_TIMEOUT) -> Optional[dict]:
    """Fetch a URL and parse JSON. Returns None on any failure."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    try:
        return json.loads(data)
    except (json.JSONDecodeError, ValueError):
        return None


# ── LCCN normalisation ────────────────────────────────────────────────────────


def _normalise_lccn(lccn: str) -> str:
    """Strip whitespace and hyphens; keep alphanumerics. Empty string if invalid."""
    if not lccn:
        return ""
    cleaned = re.sub(r"[\s\-]", "", lccn.strip())
    # LC accepts a wide variety of LCCN forms in the /item/ URL — the most
    # common are pure numeric (e.g. 2024012345) and prefixed (e.g. n2024012345).
    # We do not further canonicalise; LC's resolver handles common forms.
    return cleaned


# ── Field extraction ──────────────────────────────────────────────────────────


_LCC_CALLNUMBER_RE = re.compile(r"^[A-Z]{1,3}[0-9]")  # quick sanity: LC class numbers start like this


def _pick_lcc_call_number(call_numbers: list) -> Optional[str]:
    """From a list of catalog call-number strings, return the first that looks
    like an LCC class number (starts with 1–3 capital letters then a digit).

    LC records can also contain Dewey, MARC holdings notes, etc. — those are
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


# ── Public lookups ────────────────────────────────────────────────────────────


def lookup_by_lccn(lccn: str, timeout: float = _DEFAULT_TIMEOUT) -> Optional[CatalogHit]:
    """Resolve an LCCN to a confirmed LC call number, or None on miss / error."""
    norm = _normalise_lccn(lccn)
    if not norm:
        return None
    url = f"https://www.loc.gov/item/{urllib.parse.quote(norm)}/?fo=json"
    data = _http_get_json(url, timeout=timeout)
    if not data:
        return None
    item = data.get("item") or {}
    call = _pick_lcc_call_number(item.get("call_number") or [])
    if not call:
        return None
    return CatalogHit(
        call_number=call,
        source=f"LC catalog (LCCN {norm})",
        raw_lccn=norm,
    )


def lookup_by_isbn(isbn: str, timeout: float = _DEFAULT_TIMEOUT) -> Optional[CatalogHit]:
    """Resolve an ISBN to a confirmed LC call number, or None on miss / error.

    Searches the /books/ endpoint specifically (more reliable for
    bibliographic records than the general /search/).
    """
    if not isbn:
        return None
    cleaned = re.sub(r"[\s\-]", "", isbn.strip())
    if not cleaned:
        return None
    params = urllib.parse.urlencode({
        "q": cleaned,
        "fo": "json",
        "c": "1",
    })
    url = f"https://www.loc.gov/books/?{params}"
    data = _http_get_json(url, timeout=timeout)
    if not data:
        return None
    results = data.get("results") or []
    if not results:
        return None
    first = results[0] or {}
    call = _pick_lcc_call_number(first.get("call_number") or [])
    if not call:
        return None
    return CatalogHit(
        call_number=call,
        source=f"LC catalog (ISBN {cleaned})",
    )


def lookup_by_isbn_openlibrary(isbn: str, timeout: float = _DEFAULT_TIMEOUT) -> Optional[CatalogHit]:
    """Resolve an ISBN to an LC call number via Open Library. Confidence: medium.

    Used as a fallback when the LC catalog misses (e.g. recent publications
    not yet fully catalogued by LC).
    """
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
    data = _http_get_json(url, timeout=timeout)
    if not data:
        return None
    # Response is keyed by "ISBN:{cleaned}"
    record = data.get(f"ISBN:{cleaned}") or {}
    lc_classes = (record.get("classifications") or {}).get("lc_classifications") or []
    call = _pick_lcc_call_number(lc_classes)
    if not call:
        return None
    return CatalogHit(
        call_number=call,
        source=f"Open Library (ISBN {cleaned})",
    )


def lookup_book(identifiers: dict, timeout: float = _DEFAULT_TIMEOUT) -> Optional[CatalogHit]:
    """Try LCCN → LC ISBN → Open Library ISBN. Returns None if all miss.

    identifiers is the {type: value} dict from db.get_identifiers().
    """
    if not identifiers:
        return None

    # LCCN is the gold standard — try first.
    lccn = identifiers.get("lccn") or identifiers.get("LCCN")
    if lccn:
        hit = lookup_by_lccn(lccn, timeout=timeout)
        if hit:
            return hit

    # Try LC's books catalog by ISBN.
    for key in ("isbn", "isbn13", "isbn10", "ISBN"):
        isbn = identifiers.get(key)
        if isbn:
            hit = lookup_by_isbn(isbn, timeout=timeout)
            if hit:
                return hit

    # Fall back to Open Library as a secondary source.
    for key in ("isbn", "isbn13", "isbn10", "ISBN"):
        isbn = identifiers.get(key)
        if isbn:
            hit = lookup_by_isbn_openlibrary(isbn, timeout=timeout)
            if hit:
                return hit

    return None
