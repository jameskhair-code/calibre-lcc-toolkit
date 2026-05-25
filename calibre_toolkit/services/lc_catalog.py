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

  • https://openlibrary.org/isbn/{isbn}.json
      Single OL edition record. Returns `works: [{key: "/works/OLxxxW"}]`
      pointing at the canonical work — the bridge into the edition
      cascade. Used to discover sibling editions (different ISBNs of the
      same work) so a UK ISBN that misses LC can re-roll against the US
      edition's ISBN. See `lookup_by_isbn_with_edition_cascade`.

  • https://openlibrary.org/works/{wid}/editions.json
      All editions of a work. Returns paginated edition records each
      carrying their own `isbn_10` / `isbn_13`. We re-run LC ISBN lookup
      against each candidate.

  • https://lx2.loc.gov/sru/?...
      LC's SRU search endpoint. Title+author search of last resort when
      no ISBN-driven path returns anything. Returns MARCXML; we parse
      the 050 datafield (LC call number).

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
import xml.etree.ElementTree as ET
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
    source: str             # short label: "LC catalog (LCCN 2024012345)" etc.
    raw_lccn: str = ""      # the LCCN we used, if any (for traceability)


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
            # 4xx = permanent (bad LCCN/ISBN); 5xx = transient → retry.
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
            description=f"LC/OL HTTP GET {urllib.parse.urlparse(url).netloc}",
        )
    except _TransientHTTPError:
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


def lookup_by_lccn(
    lccn: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[CatalogHit]:
    """Resolve an LCCN to a confirmed LC call number, or None on miss / error."""
    norm = _normalise_lccn(lccn)
    if not norm:
        return None
    url = f"https://www.loc.gov/item/{urllib.parse.quote(norm)}/?fo=json"
    data = _http_get_json(url, timeout=timeout, max_retries=max_retries)
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


def lookup_by_isbn(
    isbn: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[CatalogHit]:
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
    data = _http_get_json(url, timeout=timeout, max_retries=max_retries)
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


def lookup_by_isbn_openlibrary(
    isbn: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[CatalogHit]:
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
    data = _http_get_json(url, timeout=timeout, max_retries=max_retries)
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


# ── Open Library edition cascade ─────────────────────────────────────────────
#
# Many UK / Commonwealth / international ISBNs miss LC's books catalog even
# when the work itself is well-catalogued — LC keys off the specific edition
# ISBN, and the British edition of a novel often has a different ISBN from
# the US edition that LC actually holds. The cascade walks OL's
# edition graph to discover sibling ISBNs of the same work and re-rolls
# the LC ISBN lookup against them. See ROADMAP item 12.
#
# Bounded by `_EDITION_CASCADE_MAX_ISBNS` so a work with 50 reprints does
# not produce 50 HTTP round trips. The English-first ordering means the
# first few siblings almost always include the US first-edition ISBN —
# which is what LC actually holds. 3 sibling tries captures essentially
# all the hit-rate benefit while keeping worst-case cost predictable
# when LC is slow or unreachable.

_EDITION_CASCADE_MAX_ISBNS = 3


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
    present) on the theory that LC is more likely to hold them. ISBN-13
    are preferred over ISBN-10 — they are more recent and tend to match
    LC's index better.
    """
    if not work_key or not work_key.startswith("/works/"):
        return []
    url = f"https://openlibrary.org{work_key}/editions.json"
    data = _http_get_json(url, timeout=timeout, max_retries=max_retries)
    if not data:
        return []
    entries = data.get("entries") or []
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

    # English first, then others, bounded.
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
    """Try LC ISBN lookup against sibling ISBNs of the same OL work.

    Called only after the direct LC ISBN lookup for `isbn` has already
    missed. Resolves the OL work, fetches its editions, and re-runs
    `lookup_by_isbn()` against each sibling ISBN. Returns the first hit
    (with a source string that records the cascade), or None.
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
        hit = lookup_by_isbn(sib, timeout=timeout, max_retries=max_retries)
        if hit:
            return CatalogHit(
                call_number=hit.call_number,
                source=(
                    f"LC catalog via OL edition cascade "
                    f"(seed ISBN {isbn}, matched sibling {sib})"
                ),
            )
    return None


# ── LC SRU title+author search ───────────────────────────────────────────────
#
# Last resort when every ISBN-driven path has missed. The SRU endpoint
# returns MARCXML — we parse the 050 datafield (LC class number).

_MARC_NAMESPACE = "http://www.loc.gov/MARC21/slim"
_MARC_NS = {"marc": _MARC_NAMESPACE}


def _sru_quote(value: str) -> str:
    """SRU CQL-quote a string: wrap in double quotes, escape inner quotes."""
    escaped = (value or "").replace('"', '\\"').strip()
    return f'"{escaped}"'


def _http_get_text(
    url: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[str]:
    """Like _http_get_json but returns the raw response body as text. Used
    for XML endpoints (SRU)."""

    def _attempt() -> Optional[str]:
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
            return data.decode("utf-8", errors="replace")
        except Exception:
            return None

    try:
        return retry_with_backoff(
            _attempt,
            max_retries=max_retries,
            retry_on=(_TransientHTTPError,),
            description=f"LC SRU HTTP GET {urllib.parse.urlparse(url).netloc}",
        )
    except _TransientHTTPError:
        return None


def _extract_call_number_from_marcxml(xml_text: str) -> Optional[str]:
    """Parse MARCXML and return the first LCC-shaped value from any 050
    datafield. The 050 carries the LC class number; subfield 'a' is the
    main class portion, 'b' the Cutter/year suffix.
    """
    if not xml_text:
        return None
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    # Iterate any datafield with tag=050 in any record. ElementTree's
    # findall with namespace prefixes requires the namespace map.
    for datafield in root.iter(f"{{{_MARC_NAMESPACE}}}datafield"):
        if datafield.get("tag") != "050":
            continue
        a_parts: list[str] = []
        b_parts: list[str] = []
        for sub in datafield.findall("marc:subfield", _MARC_NS):
            code = sub.get("code")
            text = (sub.text or "").strip()
            if not text:
                continue
            if code == "a":
                a_parts.append(text)
            elif code == "b":
                b_parts.append(text)
        if not a_parts:
            continue
        combined = " ".join(a_parts + b_parts).strip()
        picked = _pick_lcc_call_number([combined])
        if picked:
            return picked
    return None


def lookup_by_title_author_sru(
    title: str,
    author: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[CatalogHit]:
    """Title+author search via LC's SRU endpoint as a last-resort path.

    Returns None when title and author are both missing — the SRU
    endpoint will accept either alone, but a single-field search is
    almost always too broad to trust.
    """
    title = (title or "").strip()
    author = (author or "").strip()
    if not title or not author:
        return None
    query = f"bath.title={_sru_quote(title)} AND bath.author={_sru_quote(author)}"
    params = urllib.parse.urlencode({
        "version": "1.1",
        "operation": "searchRetrieve",
        "query": query,
        "maximumRecords": "1",
        "recordSchema": "marcxml",
    })
    url = f"https://lx2.loc.gov/sru/?{params}"
    body = _http_get_text(url, timeout=timeout, max_retries=max_retries)
    if not body:
        return None
    call = _extract_call_number_from_marcxml(body)
    if not call:
        return None
    return CatalogHit(
        call_number=call,
        source=f"LC SRU title+author ({title} / {author})",
    )


# ── Public orchestration ─────────────────────────────────────────────────────


def lookup_book(
    identifiers: dict,
    title: str = "",
    author: str = "",
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> Optional[CatalogHit]:
    """Cascade through every available lookup path for one book.

    Order (each step runs only if the previous missed):
      1. LCCN  — gold standard.
      2. LC ISBN — direct match for any ISBN on the book.
      3. OL edition cascade — for each ISBN, walk OL's work graph to
         find sibling ISBNs (other editions of the same work) and
         retry LC ISBN lookup. Catches UK/Commonwealth editions whose
         specific ISBN isn't in LC but whose US sibling is.
      4. LC SRU title+author search — last resort, when no ISBN path
         hit anything. Requires both title and author.
      5. Open Library direct ISBN — community-sourced LCC, medium
         confidence.

    identifiers is the {type: value} dict from db.get_identifiers().
    """
    if not identifiers and not (title and author):
        return None

    identifiers = identifiers or {}

    # 1. LCCN.
    lccn = identifiers.get("lccn") or identifiers.get("LCCN")
    if lccn:
        hit = lookup_by_lccn(lccn, timeout=timeout, max_retries=max_retries)
        if hit:
            return hit

    # 2. Direct LC ISBN.
    isbn_values: list[str] = []
    for key in ("isbn", "isbn13", "isbn10", "ISBN"):
        v = identifiers.get(key)
        if v and v not in isbn_values:
            isbn_values.append(v)
    for isbn in isbn_values:
        hit = lookup_by_isbn(isbn, timeout=timeout, max_retries=max_retries)
        if hit:
            return hit

    # 3. OL edition cascade — retry LC with sibling ISBNs of the same work.
    for isbn in isbn_values:
        hit = lookup_by_isbn_with_edition_cascade(
            isbn, timeout=timeout, max_retries=max_retries,
        )
        if hit:
            return hit

    # 4. LC SRU title+author search. Requires both.
    if title and author:
        hit = lookup_by_title_author_sru(
            title, author, timeout=timeout, max_retries=max_retries,
        )
        if hit:
            return hit

    # 5. Open Library direct ISBN — community-sourced, medium confidence.
    for isbn in isbn_values:
        hit = lookup_by_isbn_openlibrary(
            isbn, timeout=timeout, max_retries=max_retries,
        )
        if hit:
            return hit

    return None
