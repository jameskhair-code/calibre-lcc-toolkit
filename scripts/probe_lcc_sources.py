#!/usr/bin/env python3
"""
LCC alternative-source probe (ROADMAP item 12a research).

Runs against the user's Calibre library. Picks the books flagged in
the metadata queue (`#metadata_queue:true`), pulls their ISBNs, and
queries every candidate non-LC source we know of. Reports hit rate
and sample call numbers so we can decide whether any single source —
or some combination — could replace the LC catalog dependency
altogether.

Sources probed:

  1. HathiTrust brief        — `catalog.hathitrust.org/api/volumes/brief/isbn/{isbn}.json`
                                Indirect: returns LCCNs and OCLC numbers when LC cataloged
                                the book. Not a direct LCC hit but tells us LC has it.
  2. HathiTrust full         — `catalog.hathitrust.org/api/volumes/full/isbn/{isbn}.json`
                                Returns full MARCXML; we parse 050$a / 050$b for the
                                LC call number. THIS is the primary candidate to
                                replace `services/lc_catalog.lookup_by_isbn`.
  3. Open Library direct     — already in our cascade today (baseline).
  4. Open Library deeper     — walks the work's edition graph with max_isbns=10
                                (we currently cap at 3). Measures whether the
                                tighter cap is leaving hits on the table.
  5. Internet Archive bib    — `archive.org/wayback/available?url=...` / openlibrary search
                                surfaces LC classifications for digitized titles.

Hermetic-friendly — no pytest interaction, just stdlib + the toolkit's
own services. Run locally; nothing is written to Calibre.

Output:
  - Per-ISBN diagnostic line in stdout.
  - Summary table at the end (hit rate per source).
  - Full results dumped to `reports/lcc-probe-{timestamp}.json` for
    postmortem.

Usage:
  py scripts/probe_lcc_sources.py                       # default: read from config.json
  py scripts/probe_lcc_sources.py --config path/to/config.json
  py scripts/probe_lcc_sources.py --limit 5             # smaller dry run
  py scripts/probe_lcc_sources.py --search '<query>'    # custom Calibre search
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add the project root to sys.path so we can import calibre_toolkit when
# the script is run directly.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from calibre_toolkit.db import CalibreDB  # noqa: E402
from calibre_toolkit.services.lc_catalog import (  # noqa: E402
    _pick_lcc_call_number,
    lookup_by_isbn_openlibrary,
    _ol_work_key_for_isbn,
    _ol_sibling_isbns_for_work,
)


_USER_AGENT = "calibre-toolkit-lcc-probe/1.0 (personal research)"
_TIMEOUT = 15.0
_MARC_NS = "http://www.loc.gov/MARC21/slim"


def _http_get(url: str, timeout: float = _TIMEOUT) -> tuple[int, bytes]:
    """Minimal HTTP GET. Returns (status_code, body_bytes). Status -1 means
    no response at all (network error, timeout, etc)."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        return -1, b""


def _normalise_isbn(isbn: str) -> str:
    return re.sub(r"[\s\-]", "", (isbn or "").strip())


# ── HathiTrust ───────────────────────────────────────────────────────────────


def probe_hathitrust_brief(isbn: str) -> dict[str, Any]:
    """Return what HathiTrust's brief endpoint knows about an ISBN.

    The response shape is documented at
    https://www.hathitrust.org/bib_api — keyed by record id.
    """
    cleaned = _normalise_isbn(isbn)
    if not cleaned:
        return {"hit": False, "reason": "empty isbn"}
    url = f"https://catalog.hathitrust.org/api/volumes/brief/isbn/{urllib.parse.quote(cleaned)}.json"
    status, body = _http_get(url)
    if status != 200 or not body:
        return {"hit": False, "status": status, "reason": "http"}
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {"hit": False, "reason": "json parse"}
    records = data.get("records") or {}
    if not records:
        return {"hit": False, "reason": "no records"}
    # Pick the first record's metadata
    first_id, first = next(iter(records.items()))
    return {
        "hit": True,
        "record_id": first_id,
        "lccns": first.get("lccns") or [],
        "oclcs": first.get("oclcs") or [],
        "title": (first.get("titles") or [""])[0],
        "publish_dates": first.get("publishDates") or [],
    }


def probe_hathitrust_full(isbn: str) -> dict[str, Any]:
    """Hit the FULL endpoint and parse the MARCXML 050 datafield.

    This is the direct ISBN → LC call number path that the probe is
    centrally testing. If hit rate is decent, this is our LC replacement.
    """
    cleaned = _normalise_isbn(isbn)
    if not cleaned:
        return {"hit": False, "reason": "empty isbn"}
    url = f"https://catalog.hathitrust.org/api/volumes/full/isbn/{urllib.parse.quote(cleaned)}.json"
    status, body = _http_get(url)
    if status != 200 or not body:
        return {"hit": False, "status": status, "reason": "http"}
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {"hit": False, "reason": "json parse"}
    records = data.get("records") or {}
    if not records:
        return {"hit": False, "reason": "no records"}

    call_numbers: list[str] = []
    for record_id, rec in records.items():
        marc_xml = rec.get("marc-xml") or ""
        if not marc_xml:
            continue
        try:
            root = ET.fromstring(marc_xml)
        except ET.ParseError:
            continue
        for datafield in root.iter(f"{{{_MARC_NS}}}datafield"):
            if datafield.get("tag") != "050":
                continue
            a_parts: list[str] = []
            b_parts: list[str] = []
            for sub in datafield.findall(f"{{{_MARC_NS}}}subfield"):
                code = sub.get("code")
                text = (sub.text or "").strip()
                if not text:
                    continue
                if code == "a":
                    a_parts.append(text)
                elif code == "b":
                    b_parts.append(text)
            if a_parts:
                combined = " ".join(a_parts + b_parts).strip()
                call_numbers.append(combined)
    if not call_numbers:
        return {"hit": False, "reason": "no 050 in any record"}

    # Pick the first that parses as LCC-shaped
    picked = _pick_lcc_call_number(call_numbers)
    return {
        "hit": picked is not None,
        "call_number": picked,
        "all_050s": call_numbers,
    }


# ── Open Library (already in production cascade) ────────────────────────────


def probe_openlibrary_direct(isbn: str) -> dict[str, Any]:
    """The baseline path we already use. Included so we can measure
    incremental lift from other sources rather than double-counting OL
    hits as "new"."""
    cleaned = _normalise_isbn(isbn)
    if not cleaned:
        return {"hit": False, "reason": "empty isbn"}
    hit = lookup_by_isbn_openlibrary(cleaned)
    if hit is None:
        return {"hit": False}
    return {"hit": True, "call_number": hit.call_number, "source": hit.source}


def probe_openlibrary_deeper_cascade(isbn: str, max_isbns: int = 10) -> dict[str, Any]:
    """Walk OL's edition graph more aggressively than our production cap
    (3). Doesn't retry against LC since LC is Cloudflare-blocked anyway —
    instead, checks each sibling against OL's own classifications field.
    Measures whether deeper walking finds OL records that have LC
    classifications even when the seed ISBN's record didn't."""
    cleaned = _normalise_isbn(isbn)
    if not cleaned:
        return {"hit": False, "reason": "empty isbn"}
    work_key = _ol_work_key_for_isbn(cleaned)
    if not work_key:
        return {"hit": False, "reason": "no work key"}
    siblings = _ol_sibling_isbns_for_work(
        work_key, excluded_isbn=cleaned, max_isbns=max_isbns,
    )
    if not siblings:
        return {"hit": False, "reason": "no siblings", "work_key": work_key}

    for sib in siblings:
        hit = lookup_by_isbn_openlibrary(sib)
        if hit is not None:
            return {
                "hit": True,
                "call_number": hit.call_number,
                "matched_sibling": sib,
                "work_key": work_key,
                "siblings_tried": siblings.index(sib) + 1,
                "siblings_total": len(siblings),
            }
    return {
        "hit": False,
        "reason": "no sibling has lc_classifications",
        "work_key": work_key,
        "siblings_total": len(siblings),
    }


# ── Result aggregation ───────────────────────────────────────────────────────


@dataclass
class _BookProbe:
    book_id: int
    title: str
    authors: list[str]
    isbn: str
    hathitrust_brief: dict[str, Any] = field(default_factory=dict)
    hathitrust_full:  dict[str, Any] = field(default_factory=dict)
    openlibrary_direct: dict[str, Any] = field(default_factory=dict)
    openlibrary_deeper: dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0


def _summarize(probes: list[_BookProbe]) -> None:
    n = len(probes)
    if n == 0:
        print("\nNo books probed.")
        return

    def _count(getter) -> int:
        return sum(1 for p in probes if getter(p))

    ht_brief_hits  = _count(lambda p: p.hathitrust_brief.get("hit"))
    ht_full_hits   = _count(lambda p: p.hathitrust_full.get("hit"))
    ol_direct_hits = _count(lambda p: p.openlibrary_direct.get("hit"))
    ol_deeper_hits = _count(lambda p: p.openlibrary_deeper.get("hit"))

    # "Any LC call number from non-LC source" — the actual question.
    any_non_lc_hit = _count(
        lambda p:
            p.hathitrust_full.get("hit")
            or p.openlibrary_direct.get("hit")
            or p.openlibrary_deeper.get("hit")
    )

    def pct(n_hits: int) -> str:
        return f"{n_hits:>2}/{n} ({100 * n_hits / n:5.1f}%)"

    print()
    print("═" * 72)
    print("SUMMARY — Can we get LC call numbers WITHOUT hitting LC directly?")
    print("═" * 72)
    print()
    print(f"  HathiTrust brief (LCCN seen):              {pct(ht_brief_hits)}")
    print(f"  HathiTrust full  (050 datafield extracted): {pct(ht_full_hits)}")
    print(f"  Open Library direct (baseline):            {pct(ol_direct_hits)}")
    print(f"  Open Library deeper cascade (max=10):      {pct(ol_deeper_hits)}")
    print()
    print(f"  ── Any non-LC source produced a call number: {pct(any_non_lc_hit)}")
    print()

    # Sample some hits and misses so we can eyeball quality.
    print("─ Sample hits (call number returned) ─")
    shown = 0
    for p in probes:
        if shown >= 5:
            break
        winners = []
        if p.hathitrust_full.get("hit"):
            winners.append(("HT-full", p.hathitrust_full.get("call_number", "")))
        if p.openlibrary_direct.get("hit"):
            winners.append(("OL-direct", p.openlibrary_direct.get("call_number", "")))
        if p.openlibrary_deeper.get("hit"):
            winners.append(("OL-deeper", p.openlibrary_deeper.get("call_number", "")))
        if not winners:
            continue
        author = p.authors[0] if p.authors else "(no author)"
        print(f"  • {p.title[:50]:50s}  {author[:25]:25s}")
        for src, cn in winners:
            print(f"      {src:10s} {cn}")
        shown += 1

    print()
    print("─ Sample misses (every source missed) ─")
    shown = 0
    for p in probes:
        if shown >= 5:
            break
        if any([
            p.hathitrust_full.get("hit"),
            p.openlibrary_direct.get("hit"),
            p.openlibrary_deeper.get("hit"),
        ]):
            continue
        author = p.authors[0] if p.authors else "(no author)"
        print(f"  • {p.title[:50]:50s}  {author[:25]:25s}  ISBN: {p.isbn}")
        shown += 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument(
        "--config", default="config.json",
        help="Path to config.json (defaults to ./config.json).",
    )
    p.add_argument(
        "--search", default="#metadata_queue:true",
        help="Calibre search query selecting the books to probe.",
    )
    p.add_argument(
        "--limit", type=int, default=None,
        help="Cap the number of books probed (after search).",
    )
    p.add_argument(
        "--reports-dir", default="reports",
        help="Directory to write the raw JSON results.",
    )
    args = p.parse_args(argv)

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"config not found: {cfg_path}", file=sys.stderr)
        return 1
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    db = CalibreDB(
        library_path=cfg["library_path"],
        calibredb_path=cfg.get("calibredb_path", "calibredb"),
    )

    print(f"Searching: {args.search}")
    books = db.search(args.search)
    if args.limit:
        books = books[: args.limit]
    if not books:
        print("No books matched.")
        return 0
    print(f"Probing {len(books)} book(s) across HathiTrust + Open Library …")
    print()

    probes: list[_BookProbe] = []
    for i, book in enumerate(books, 1):
        ids = db.get_identifiers(book.id)
        isbn = (
            ids.get("isbn") or ids.get("isbn13") or ids.get("isbn10") or ""
        )
        author = book.authors[0] if book.authors else ""
        print(f"[{i:>2}/{len(books)}] {book.title[:55]:55s}  {author[:22]:22s}  ISBN: {isbn or '(none)'}")
        t0 = time.monotonic()
        probe = _BookProbe(
            book_id=book.id,
            title=book.title,
            authors=list(book.authors),
            isbn=isbn,
        )
        if isbn:
            probe.hathitrust_brief = probe_hathitrust_brief(isbn)
            probe.hathitrust_full = probe_hathitrust_full(isbn)
            probe.openlibrary_direct = probe_openlibrary_direct(isbn)
            probe.openlibrary_deeper = probe_openlibrary_deeper_cascade(isbn)
        else:
            probe.hathitrust_brief = {"hit": False, "reason": "no isbn"}
            probe.hathitrust_full = {"hit": False, "reason": "no isbn"}
            probe.openlibrary_direct = {"hit": False, "reason": "no isbn"}
            probe.openlibrary_deeper = {"hit": False, "reason": "no isbn"}
        probe.elapsed_seconds = round(time.monotonic() - t0, 2)
        probes.append(probe)

        # One-line per-source verdict for this book.
        flags = []
        flags.append("HT-brief✓" if probe.hathitrust_brief.get("hit") else "HT-brief·")
        flags.append("HT-full✓"  if probe.hathitrust_full.get("hit")  else "HT-full·")
        flags.append("OL-direct✓" if probe.openlibrary_direct.get("hit") else "OL-direct·")
        flags.append("OL-deeper✓" if probe.openlibrary_deeper.get("hit") else "OL-deeper·")
        print(f"          {'  '.join(flags)}   ({probe.elapsed_seconds:.1f}s)")

    _summarize(probes)

    # Persist raw results so we can post-mortem without re-running.
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = reports_dir / f"lcc-probe-{ts}.json"
    out_path.write_text(
        json.dumps([asdict(p) for p in probes], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print()
    print(f"Raw results saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
