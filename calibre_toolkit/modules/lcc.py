"""
MQG-03 LCC Enrichment — pure domain logic.

Call-number parsing, canonical-CSV validation, the LC catalog pre-lookup,
catalog-hit suggestion building, AI-only truncation, and the renderable
builders. The lcc-enrich orchestration (search → lookup → AI → review →
apply) lives in `commands/lcc_enrich.py`.
"""

from __future__ import annotations

import csv
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box

from ..ai import AIClient, LccSuggestion
from ..db import CalibreDB
from ..logging_config import get_logger
from ..services.book_description import BookDescription
from ..services.lc_catalog import CatalogHit, lookup_book


console = Console()
_log = get_logger(__name__)

# ── Canonical CSV loading ─────────────────────────────────────────────────────

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
_PRIMARY_CSV = _CONFIG_DIR / "lcc-primary-canonical.csv"
_SECONDARY_CSV = _CONFIG_DIR / "lcc-secondary-canonical.csv"


def _load_canonical(csv_path: Path) -> dict[str, str]:
    """Return {Code: CanonicalValue} from a canonical CSV."""
    mapping: dict[str, str] = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row["Code"].strip()
            value = row["CanonicalValue"].strip()
            if code and value:
                mapping[code] = value
    return mapping


_PRIMARY_BY_CODE = _load_canonical(_PRIMARY_CSV)         # {"D": "D - World History / ..."}
_SECONDARY_BY_CODE = _load_canonical(_SECONDARY_CSV)     # {"DK": "DK - Russia / ...", "E11-143": "..."}
_VALID_PRIMARY = set(_PRIMARY_BY_CODE.values())
_VALID_SECONDARY = set(_SECONDARY_BY_CODE.values())


# ── LCC call number parsing ───────────────────────────────────────────────────

_LCC_PREFIX_RE = re.compile(r"^\s*([A-Z]{1,3})\s*(\d+(?:\.\d+)?)?", re.IGNORECASE)

# Matches the LCC "class portion" — letters + class number (with optional
# decimal class subdivision). Stops before any Cutter or date. Used by the
# v1.7 item-6 AI-only truncation: when no OL hit confirms the call number,
# the structured `lcc` field is reduced to the class portion only and the
# AI's unverified Cutter/year are dropped (the AI's full reasoning still
# lives in `lcc_summary`).
_LCC_CLASS_PORTION_RE = re.compile(r"^\s*([A-Z]{1,3}\s*\d+(?:\.\d+)?)", re.IGNORECASE)


def _truncate_to_class_portion(call_number: str) -> str:
    """Return only the class letters + class number (preserving any decimal
    class subdivision) from an LCC call number. Strips Cutter and date.

    Returns the input unchanged when nothing parses as an LCC class portion,
    so malformed AI output is preserved verbatim for the validator to flag.
    """
    if not call_number:
        return ""
    m = _LCC_CLASS_PORTION_RE.match(call_number)
    if not m:
        return call_number.strip()
    return re.sub(r"\s+", "", m.group(1)).upper()


def _parse_lcc_prefix(call_number: str) -> tuple[str, int | None]:
    """Return (subclass_letters, integer_class_number_or_None) from a call number.

    Examples:
        "DK189 .W67 2003"  → ("DK", 189)
        "BM197.5 .K64"     → ("BM", 197)
        "PS3563.O8749"     → ("PS", 3563)
        "DAW1051"          → ("DAW", 1051)
        "D"                → ("D", None)
        ""                 → ("", None)
    """
    m = _LCC_PREFIX_RE.match(call_number or "")
    if not m:
        return "", None
    letters = m.group(1).upper()
    num_str = m.group(2)
    if num_str is None:
        return letters, None
    # Use only the integer portion for range matching
    try:
        return letters, int(num_str.split(".")[0])
    except ValueError:
        return letters, None


# Range-coded E/F secondaries
_RANGE_SECONDARIES: list[tuple[str, int, int, str]] = [
    ("E",  11,  143,   "E11-143"),
    ("E",  151, 909,   "E151-909"),
    ("F",  1,   975,   "F1-975"),
    ("F",  1001, 1145, "F1001-1145"),
    ("F",  1170, 1170, "F1170"),
    ("F",  1201, 3799, "F1201-3799"),
]


def _derive_classes(call_number: str) -> tuple[str, str]:
    """Derive (primary_canonical, secondary_canonical) from an LCC call number.

    Returns empty strings for either field when no canonical match exists.
    """
    letters, num = _parse_lcc_prefix(call_number)
    if not letters:
        return "", ""

    primary = _PRIMARY_BY_CODE.get(letters[0], "")

    # Range-coded E/F secondaries take precedence when number falls in range
    if letters[0] in ("E", "F") and num is not None:
        for first_letter, lo, hi, code in _RANGE_SECONDARIES:
            if first_letter == letters[0] and lo <= num <= hi:
                secondary = _SECONDARY_BY_CODE.get(code, "")
                if secondary:
                    return primary, secondary

    # Combined-range K secondaries
    if letters.startswith("K"):
        if letters in ("KD", "KDK"):
            return primary, _SECONDARY_BY_CODE.get("KD-KDK", "")
        # Direct match first (KBM, KBP, KE, KF, KZ, etc.)
        if letters in _SECONDARY_BY_CODE:
            return primary, _SECONDARY_BY_CODE[letters]
        # KG-KH (Latin America & South America), KJ-KKZ (Europe), KL-KWX (Asia/Eurasia/Africa/Pacific)
        # Use explicit two-letter prefix sets to avoid alphabetic range ambiguity.
        two = letters[:2]
        if two in ("KG", "KH"):
            return primary, _SECONDARY_BY_CODE.get("KG-KH", "")
        if two in ("KJ", "KK"):
            return primary, _SECONDARY_BY_CODE.get("KJ-KKZ", "")
        if "KL" <= two <= "KW":
            return primary, _SECONDARY_BY_CODE.get("KL-KWX", "")

    # Try 3-letter (DAW, DJK), then 2-letter
    if len(letters) >= 3 and letters in _SECONDARY_BY_CODE:
        return primary, _SECONDARY_BY_CODE[letters]
    if len(letters) >= 2 and letters[:2] in _SECONDARY_BY_CODE:
        return primary, _SECONDARY_BY_CODE[letters[:2]]
    # Single-letter fallback
    if letters[:1] in _SECONDARY_BY_CODE:
        return primary, _SECONDARY_BY_CODE[letters[:1]]
    return primary, ""


# ── Validation ────────────────────────────────────────────────────────────────

@dataclass
class ValidatedSuggestion:
    """Wraps an LccSuggestion with validation results and code-derived classes."""
    suggestion: LccSuggestion
    derived_primary: str
    derived_secondary: str
    primary_mismatch: bool
    secondary_mismatch: bool
    primary_invalid: bool     # AI returned a string not in canonical list
    secondary_invalid: bool

    @property
    def book_id(self) -> int:
        return self.suggestion.book_id

    @property
    def has_warnings(self) -> bool:
        return any([self.primary_mismatch, self.secondary_mismatch,
                    self.primary_invalid, self.secondary_invalid])

    @property
    def final_fields(self) -> dict[str, str]:
        """Values to actually write — code-derived classes win over AI strings."""
        s = self.suggestion
        return {
            "lcc": s.proposed["lcc"],
            "lcc_primary_class": self.derived_primary or s.proposed["lcc_primary_class"],
            "lcc_secondary_class": self.derived_secondary or s.proposed["lcc_secondary_class"],
            "lcc_summary": s.proposed["lcc_summary"],
        }


def _validate(suggestion: LccSuggestion) -> ValidatedSuggestion:
    p = suggestion.proposed
    derived_pri, derived_sec = _derive_classes(p["lcc"])

    primary_invalid = bool(p["lcc_primary_class"]) and p["lcc_primary_class"] not in _VALID_PRIMARY
    secondary_invalid = bool(p["lcc_secondary_class"]) and p["lcc_secondary_class"] not in _VALID_SECONDARY

    primary_mismatch = bool(derived_pri) and bool(p["lcc_primary_class"]) and derived_pri != p["lcc_primary_class"]
    secondary_mismatch = bool(derived_sec) and bool(p["lcc_secondary_class"]) and derived_sec != p["lcc_secondary_class"]

    return ValidatedSuggestion(
        suggestion=suggestion,
        derived_primary=derived_pri,
        derived_secondary=derived_sec,
        primary_mismatch=primary_mismatch,
        secondary_mismatch=secondary_mismatch,
        primary_invalid=primary_invalid,
        secondary_invalid=secondary_invalid,
    )


# ── Display ───────────────────────────────────────────────────────────────────

_CONF_DISPLAY = {
    "high":   ("●", "green"),
    "medium": ("◐", "yellow"),
    "low":    ("○", "red"),
}


def _build_review_table(validated: list[ValidatedSuggestion]) -> Table:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
                  expand=True, show_lines=True)
    table.add_column("#", style="dim", width=4, no_wrap=True)
    table.add_column("Conf", width=5, no_wrap=True)
    table.add_column("Book", ratio=3)
    table.add_column("Proposed LCC fields", ratio=5)
    table.add_column("Source", ratio=2)

    for i, v in enumerate(validated, 1):
        s = v.suggestion
        icon, style = _CONF_DISPLAY.get(s.confidence, ("—", "dim"))
        conf_text = Text(icon, style=style)

        book_text = Text()
        book_text.append(s.title)
        book_text.append(f"\n{s.authors_display}", style="dim")

        prop_text = Text()
        prop_text.append("LCC:  ", style="dim")
        prop_text.append(s.proposed["lcc"] or "(empty)", style="bold")
        prop_text.append("\nPri:  ", style="dim")
        prop_text.append(v.final_fields["lcc_primary_class"], style="bold")
        if v.primary_mismatch:
            prop_text.append(f"\n      ↳ AI said: {s.proposed['lcc_primary_class']}", style="yellow")
        if v.primary_invalid:
            prop_text.append(f"\n      ↳ AI value not in canonical list", style="red")
        prop_text.append("\nSec:  ", style="dim")
        prop_text.append(v.final_fields["lcc_secondary_class"], style="bold")
        if v.secondary_mismatch:
            prop_text.append(f"\n      ↳ AI said: {s.proposed['lcc_secondary_class']}", style="yellow")
        if v.secondary_invalid:
            prop_text.append(f"\n      ↳ AI value not in canonical list", style="red")
        prop_text.append("\nPath: ", style="dim")
        prop_text.append(s.proposed["lcc_summary"] or "(empty)")

        src_text = Text()
        # Structural attribution prefix is the trustworthy provenance —
        # the AI's free-text source string can claim things we never verified.
        prefix_style = {
            "[LC]": "bold green",
            "[WC]": "bold cyan",
            "[OL]": "bold yellow",
            "[AI]": "bold magenta",
        }.get(s.attribution_prefix, "bold")
        src_text.append(s.attribution_prefix, style=prefix_style)
        src_text.append(" ")
        src_text.append(s.source or "(no source text)", style="dim italic")
        if s.notes:
            src_text.append(f"\n{s.notes}", style="dim")

        table.add_row(str(i), conf_text, book_text, prop_text, src_text)
    return table


# ── LC catalog pre-step ───────────────────────────────────────────────────────

_CATALOG_LOOKUP_WORKERS = 8
_CATALOG_LOOKUP_TIMEOUT = 10.0


@dataclass
class _CatalogStats:
    total: int = 0
    no_identifiers: int = 0
    tried_lccn: int = 0
    tried_isbn: int = 0
    hits: int = 0
    # Per-source breakdown — surfaced in the post-lookup diagnostic.
    # Two paths remain after the v1.3 LC removal: direct OL ISBN
    # lookup and the OL edition cascade (sibling ISBN walk).
    ol_direct_hits: int = 0
    ol_cascade_hits: int = 0


def _classify_hit_source(source: str) -> str:
    """Bucket a CatalogHit.source string into one of: ol_direct,
    ol_cascade, other."""
    if not source:
        return "other"
    if "edition cascade" in source:
        return "ol_cascade"
    if source.startswith("Open Library"):
        return "ol_direct"
    return "other"


def _catalog_lookup_batch(
    db: CalibreDB,
    books: list,
    timeout: float = _CATALOG_LOOKUP_TIMEOUT,
    max_retries: int = 3,
) -> tuple[dict[int, CatalogHit], _CatalogStats]:
    """Try LC catalog lookups for each book in parallel.

    Returns ({book_id: CatalogHit} for hits, stats). Misses and errors are
    simply absent from the hits dict — the caller falls back to AI.
    """
    stats = _CatalogStats(total=len(books))
    if not books:
        return {}, stats

    # Fetch identifiers in serial (SQLite reads are fast); the network calls
    # happen in the thread pool.
    id_map = {b.id: db.get_identifiers(b.id) for b in books}

    # Tally what we actually have to work with up-front.
    for ids in id_map.values():
        has_lccn = bool(ids.get("lccn") or ids.get("LCCN"))
        has_isbn = bool(ids.get("isbn") or ids.get("isbn13") or ids.get("isbn10") or ids.get("ISBN"))
        if not has_lccn and not has_isbn:
            stats.no_identifiers += 1
        if has_lccn:
            stats.tried_lccn += 1
        if has_isbn and not has_lccn:
            stats.tried_isbn += 1

    hits: dict[int, CatalogHit] = {}
    with ThreadPoolExecutor(max_workers=_CATALOG_LOOKUP_WORKERS) as ex:
        futures = {
            ex.submit(
                lookup_book,
                id_map.get(b.id, {}),
                # Title + primary author are passed in so the SRU
                # fallback (item 12) can run when every ISBN path misses.
                b.title or "",
                (b.authors[0] if b.authors else ""),
                timeout,
                max_retries,
            ): b.id
            for b in books
        }
        for fut in as_completed(futures):
            bid = futures[fut]
            try:
                hit = fut.result()
            except Exception:
                hit = None
            if not hit:
                continue
            hits[bid] = hit
            bucket = _classify_hit_source(hit.source)
            if bucket == "ol_cascade":
                stats.ol_cascade_hits += 1
            else:
                stats.ol_direct_hits += 1
    stats.hits = len(hits)
    return hits, stats


def _truncate_ai_only_lcc(suggestions: list[LccSuggestion]) -> None:
    """In-place: truncate the structured `lcc` field to the class portion
    for any AI-only suggestion (v1.7 item 6).

    The AI can identify the LC class letters reliably — those come straight
    out of standard LC subject schedules. The Cutter and date are
    educated guesses the AI cannot verify without catalog access (a v1.6
    real-library run found AI Cutters that were structurally wrong for
    the author's surname). So when no OL hit confirms the call number,
    drop the unverified Cutter/year and keep only the class portion.
    `lcc_summary` is preserved verbatim — the AI's full reasoning still
    lives there.

    Catalog-sourced suggestions (source_authority != "ai_inference") are
    unchanged: those Cutter/year strings came from member-library
    cataloging in OL, not the AI.
    """
    for s in suggestions:
        if s.source_authority != "ai_inference":
            continue
        full = s.proposed.get("lcc", "")
        truncated = _truncate_to_class_portion(full)
        if truncated != full:
            s.proposed["lcc"] = truncated


def _build_source_breakdown_extras(
    cat_stats: _CatalogStats,
    ai_suggestions: list[LccSuggestion],
) -> dict[str, dict[str, int]]:
    """v1.7 item 7: source-provenance rows for the StepSummary extras
    panel. Returns a dict shaped for `StepSummary.extras` with one
    `by_source` category whose rows are OL direct / OL cascade /
    AI-only. Zero rows are dropped (so the panel doesn't print
    "AI-only: 0" when every book hit a catalog). Returns `{}` when
    nothing was produced, in which case the panel renders no source
    row at all.

    AI-only count uses `len(ai_suggestions)` rather than `len(ai_books)`
    — failures are silent here, matching the rest of the summary,
    which only reports what was actually produced.
    """
    counts = {
        "OL direct": cat_stats.ol_direct_hits,
        "OL cascade": cat_stats.ol_cascade_hits,
        "AI-only": len(ai_suggestions),
    }
    nonzero = {k: v for k, v in counts.items() if v > 0}
    return {"by_source": nonzero} if nonzero else {}


def _apply_ai_summary_to_catalog_hits(
    ai: AIClient,
    books: list,
    catalog_suggestions: list[LccSuggestion],
    description_map: dict[int, BookDescription],
    batch_size: int,
) -> None:
    """v1.7 item 5: replace template summaries on catalog hits with
    description-grounded AI prose.

    Only fires for catalog-hit books that also have a pre-fetched
    description. Catalog-derived lcc/primary/secondary fields are not
    touched — only `lcc_summary` is rewritten. Books without a usable
    AI summary (no description, identity mismatch, AI call failure)
    keep the catalog-template summary that `_build_catalog_suggestion`
    already set.
    """
    if not catalog_suggestions:
        return

    book_by_id = {b.id: b for b in books}
    eligible_books: list = []
    catalog_context_map: dict[int, dict[str, str]] = {}
    for s in catalog_suggestions:
        b = book_by_id.get(s.book_id)
        if b is None:
            continue
        desc = description_map.get(b.id)
        if desc is None or not desc.text:
            continue
        eligible_books.append(b)
        catalog_context_map[b.id] = {
            "lcc": s.proposed.get("lcc", ""),
            "lcc_primary_class": s.proposed.get("lcc_primary_class", ""),
            "lcc_secondary_class": s.proposed.get("lcc_secondary_class", ""),
            "catalog_source": s.source,
        }

    skipped_no_desc = len(catalog_suggestions) - len(eligible_books)
    if not eligible_books:
        if skipped_no_desc:
            console.print(
                f"[dim]Catalog-hit AI summary: skipped — none of "
                f"{len(catalog_suggestions)} catalog-hit book(s) had a "
                "pre-fetched description.[/dim]"
            )
        return

    console.print(
        f"[cyan]Generating description-grounded summaries for "
        f"[bold]{len(eligible_books)}[/bold] catalog-hit book(s)…[/cyan]"
    )

    try:
        summary_map = ai.suggest_lcc_summary(
            eligible_books,
            catalog_context_map=catalog_context_map,
            description_map=description_map,
            batch_size=batch_size,
        )
    except (RuntimeError, Exception) as e:  # noqa: BLE001 — defensive: keep template summaries on any failure
        _log.warning("Catalog-hit AI summary failed (%s); keeping template summaries.", e)
        console.print(
            f"[dim]Catalog-hit AI summary failed ({type(e).__name__}); "
            "keeping the template summaries for those books.[/dim]"
        )
        return

    applied = 0
    for s in catalog_suggestions:
        prose = summary_map.get(s.book_id)
        if prose:
            s.proposed["lcc_summary"] = prose
            applied += 1

    parts = [f"{applied}/{len(eligible_books)} replaced with AI prose"]
    fallbacks = len(eligible_books) - applied
    if fallbacks:
        parts.append(f"{fallbacks} kept template (identity mismatch or empty AI)")
    if skipped_no_desc:
        parts.append(f"{skipped_no_desc} kept template (no description)")
    console.print(f"[dim]Catalog-hit summaries: {'; '.join(parts)}.[/dim]")


def _build_catalog_suggestion(
    book,
    current: dict[str, str],
    hit: CatalogHit,
) -> LccSuggestion:
    """Build an LccSuggestion directly from a catalog hit. Bypasses the AI.

    Every catalog hit currently comes from Open Library (direct or via
    the edition cascade) — community-sourced LC classification data,
    rated medium confidence. The LC direct paths were removed in v1.3
    after Cloudflare made them unreachable; see
    docs/LC-Cloudflare-Investigation.md.
    """
    primary, secondary = _derive_classes(hit.call_number)
    summary_class = secondary or primary or "Library of Congress Classification"
    summary = f"Classified by Open Library under {summary_class}."

    proposed = {
        "lcc": hit.call_number,
        "lcc_primary_class": primary,
        "lcc_secondary_class": secondary,
        "lcc_summary": summary,
    }
    return LccSuggestion(
        book_id=book.id,
        title=book.title,
        authors=book.authors,
        current=current,
        proposed=proposed,
        confidence="medium",
        source=hit.source,
        notes="Open Library classification; AI bypassed.",
        source_authority="open_library",
    )


# ── DB helpers ────────────────────────────────────────────────────────────────

_LCC_FIELDS = ("lcc", "lcc_primary_class", "lcc_secondary_class", "lcc_summary")


def _read_current(db: CalibreDB, book_ids: list[int], columns: dict[str, str]) -> dict[int, dict[str, str]]:
    """Read current LCC field values for many books.

    columns maps logical field name → custom column label (e.g. "lcc" → "#lcc").
    Returns {book_id: {field: value}} including books with empty values
    (so the AI can see they're missing).
    """
    out: dict[int, dict[str, str]] = {bid: {k: "" for k in _LCC_FIELDS} for bid in book_ids}
    for field_name in _LCC_FIELDS:
        label = columns.get(field_name)
        if not label:
            continue
        batch = db.get_custom_column_batch(book_ids, label)
        for bid, val in batch.items():
            out[bid][field_name] = val or ""
    return out


# ── Audit display ─────────────────────────────────────────────────────────────

def _build_audit_table(
    validated: list[ValidatedSuggestion],
    current_map: dict[int, dict[str, str]],
) -> Table:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
                  expand=True, show_lines=True)
    table.add_column("#",        style="dim", width=4, no_wrap=True)
    table.add_column("Conf",     width=5, no_wrap=True)
    table.add_column("Book",     ratio=2)
    table.add_column("Current",  ratio=4)
    table.add_column("Proposed", ratio=4)
    table.add_column("Δ",        width=5, no_wrap=True)

    _LABELS = [("LCC",  "lcc"),
               ("Pri",  "lcc_primary_class"),
               ("Sec",  "lcc_secondary_class"),
               ("Summary", "lcc_summary")]

    for i, v in enumerate(validated, 1):
        s = v.suggestion
        current = current_map.get(s.book_id, {})
        proposed = v.final_fields

        icon, style = _CONF_DISPLAY.get(s.confidence, ("—", "dim"))

        book_text = Text()
        book_text.append(s.title)
        book_text.append(f"\n{s.authors_display}", style="dim")

        cur_text  = Text()
        prop_text = Text()
        changed: list[str] = []

        for label, key in _LABELS:
            cur_val  = current.get(key,  "") or ""
            prop_val = proposed.get(key, "") or ""
            match = cur_val == prop_val

            cur_text.append(f"{label}: ", style="dim")
            cur_text.append(cur_val or "(empty)", style="green" if match else "yellow")
            cur_text.append("\n")

            prop_text.append(f"{label}: ", style="dim")
            prop_text.append(prop_val or "(empty)", style="green" if match else "bold white")
            prop_text.append("\n")

            if not match:
                changed.append(label)

        delta = Text("✓", style="green") if not changed else Text(f"Δ{len(changed)}", style="yellow")

        table.add_row(str(i), Text(icon, style=style), book_text, cur_text, prop_text, delta)

    return table
