"""
MQG-03 LCC Enrichment module.
Orchestrates: read current LCC fields → LC catalog lookup (LCCN/ISBN) →
AI propose for remaining → validate against canonical CSVs → display
review table → confirm → apply via calibredb.
"""

from __future__ import annotations

import csv
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.prompt import Prompt

from ..ai import AIClient, LccSuggestion
from ..db import CalibreDB
from ..logging_config import audit_log, get_logger
from ..services.book_description import BookDescription, fetch_descriptions_batch
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
    # Per-source breakdown — surfaced in the post-lookup diagnostic so the
    # impact of the v1.3 ISBN cross-reference work (item 12) is visible.
    direct_hits: int = 0       # LCCN or direct LC ISBN.
    cascade_hits: int = 0      # LC ISBN via OL edition cascade (sibling ISBN).
    sru_hits: int = 0          # LC SRU title+author fallback.
    ol_hits: int = 0           # OL community-sourced LCC, medium confidence.


def _classify_hit_source(source: str) -> str:
    """Bucket a CatalogHit.source string into one of: lccn, isbn, cascade,
    sru, ol, other."""
    if not source:
        return "other"
    if source.startswith("Open Library"):
        return "ol"
    if "edition cascade" in source:
        return "cascade"
    if source.startswith("LC SRU"):
        return "sru"
    if "LCCN" in source:
        return "lccn"
    if source.startswith("LC catalog"):
        return "isbn"
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
            if bucket == "ol":
                stats.ol_hits += 1
            elif bucket == "cascade":
                stats.cascade_hits += 1
            elif bucket == "sru":
                stats.sru_hits += 1
            else:
                stats.direct_hits += 1
    stats.hits = len(hits)
    return hits, stats


def _build_catalog_suggestion(
    book,
    current: dict[str, str],
    hit: CatalogHit,
) -> LccSuggestion:
    """Build an LccSuggestion directly from a catalog hit. Bypasses the AI.

    LC catalog hits are high-confidence; Open Library hits are medium (LC
    classification data there is community-sourced and less authoritative).
    """
    primary, secondary = _derive_classes(hit.call_number)
    summary_class = secondary or primary or "Library of Congress Classification"
    summary = f"Classified by Library of Congress catalog under {summary_class}."

    is_ol = hit.source.startswith("Open Library")
    confidence = "medium" if is_ol else "high"
    notes = "Open Library classification; AI bypassed." if is_ol else "Catalog-derived; AI bypassed."
    authority = "open_library" if is_ol else "lc_catalog"

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
        confidence=confidence,
        source=hit.source,
        notes=notes,
        source_authority=authority,
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


def _apply_suggestion(db: CalibreDB, v: ValidatedSuggestion, columns: dict[str, str]) -> None:
    fields = {}
    for field_name in _LCC_FIELDS:
        label = columns.get(field_name)
        if not label:
            continue
        fields[label] = v.final_fields[field_name]
    db.apply_custom_fields(v.book_id, fields)

    # Audit each field individually so a later analysis can grep by field.
    # `source` is the structural enum — a future audit can trust it; the
    # AI's free-text source string is preserved separately as `source_text`.
    structural_source = v.suggestion.source_authority
    source_text = v.suggestion.source or ""
    confidence = v.suggestion.confidence
    for label, value in fields.items():
        audit_log(
            book_id=v.book_id,
            field=label,
            new_value=value,
            confidence=confidence,
            source=structural_source,
            source_text=source_text,
            step="lcc-enrich",
        )
    _log.debug(
        "applied LCC suggestion for book %s (conf=%s, source=%s, prefix=%s)",
        v.book_id, confidence, structural_source, v.suggestion.attribution_prefix,
    )


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


def _print_audit_summary(
    validated: list[ValidatedSuggestion],
    current_map: dict[int, dict[str, str]],
) -> None:
    total = len(validated)
    exact_match = 0
    diff_counts: dict[str, int] = {k: 0 for k in _LCC_FIELDS}

    for v in validated:
        current  = current_map.get(v.book_id, {})
        proposed = v.final_fields
        any_diff = False
        for key in _LCC_FIELDS:
            if (current.get(key) or "") != (proposed.get(key) or ""):
                diff_counts[key] += 1
                any_diff = True
        if not any_diff:
            exact_match += 1

    differ = total - exact_match

    console.print("\n[bold]── Audit Summary ──────────────────────────────[/bold]")
    console.print(f"  Total reviewed:    [bold]{total}[/bold]")
    console.print(f"  [green]Exact match:       {exact_match}[/green]  [dim](AI agrees with current values)[/dim]")
    console.print(f"  [yellow]Have differences:  {differ}[/yellow]  [dim](AI would write something different)[/dim]")
    if differ:
        console.print("\n  [dim]Differences by field:[/dim]")
        labels = {"lcc": "LCC call number", "lcc_primary_class": "Primary class",
                  "lcc_secondary_class": "Secondary class", "lcc_summary": "LCC summary"}
        for key, count in diff_counts.items():
            if count:
                console.print(f"    {labels[key]}: [yellow]{count}[/yellow] book(s)")
    console.print("\n[dim]Dry-run complete — no changes were written.[/dim]")


# ── Orchestration ─────────────────────────────────────────────────────────────

def run_lcc_enrichment(
    db: CalibreDB,
    ai: AIClient,
    search_query: str,
    columns: dict[str, str],
    batch_size: int = 10,
    limit: int | None = None,
    auto_apply_high: bool = False,
    mqg_column: str | None = None,
    mqg_manual_column: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    catalog_timeout: float = _CATALOG_LOOKUP_TIMEOUT,
    catalog_max_retries: int = 3,
    description_timeout: float = _CATALOG_LOOKUP_TIMEOUT,
    description_max_retries: int = 3,
    google_books_api_key: str | None = None,
) -> None:
    """Full MQG-03 LCC enrichment flow for a Calibre search string.

    columns maps logical field name → custom column label:
        {"lcc": "#lcc", "lcc_primary_class": "#lcc_primary_class", ...}
    force=True processes books that already have all four fields populated.
    """
    # ── 1. Search ─────────────────────────────────────────────────────────────
    # --force overrides the manual-skip exclusion: when re-running on purpose,
    # the user wants to see books they previously declined as well.
    effective_query = (
        f"({search_query}) and not {mqg_manual_column}:true"
        if mqg_manual_column and not force else search_query
    )
    try:
        with console.status(f"[cyan]Searching library:[/] {search_query}"):
            books = db.search(effective_query)
    except RuntimeError as e:
        console.print(Panel(str(e), title="[red]Cannot access library[/red]", border_style="red"))
        raise typer.Exit(1)

    if not books:
        console.print("[yellow]No books matched that search. Nothing to do.[/yellow]")
        raise typer.Exit()

    total_matched = len(books)
    if limit and len(books) > limit:
        books = books[:limit]
        console.print(
            f"\n[bold]Found [green]{total_matched}[/green] books "
            f"— processing first [cyan]{limit}[/cyan] (--limit).[/bold]"
        )
    else:
        console.print(f"\n[bold]Found [green]{len(books)}[/green] books.[/bold]")

    # ── 2. Read current LCC values ────────────────────────────────────────────
    book_ids = [b.id for b in books]
    with console.status("[cyan]Reading current LCC fields…"):
        current_map = _read_current(db, book_ids, columns)

    # Skip books already fully populated unless --force
    if not force:
        before = len(books)
        already_populated = [b.id for b in books if all(current_map[b.id][k] for k in _LCC_FIELDS)]
        books = [b for b in books if not all(current_map[b.id][k] for k in _LCC_FIELDS)]
        skipped = before - len(books)
        if skipped:
            console.print(
                f"[dim]Skipping {skipped} book(s) — all four LCC fields already populated. "
                "Use --force to re-process them.[/dim]"
            )
            if mqg_column and already_populated:
                _mark_complete(db, mqg_column, already_populated, label="already-populated")
    if not books:
        console.print("[green]Nothing to do — every matched book is already fully populated.[/green]")
        raise typer.Exit()

    # ── 3a. LC catalog pre-lookup ─────────────────────────────────────────────
    with console.status(
        f"[cyan]Looking up {len(books)} book(s) in the LC catalog "
        "(LCCN → ISBN)…[/cyan]"
    ):
        catalog_hits, cat_stats = _catalog_lookup_batch(
            db, books,
            timeout=catalog_timeout,
            max_retries=catalog_max_retries,
        )

    catalog_suggestions: list[LccSuggestion] = []
    ai_books = []
    for b in books:
        hit = catalog_hits.get(b.id)
        if hit:
            catalog_suggestions.append(
                _build_catalog_suggestion(b, current_map[b.id], hit)
            )
        else:
            ai_books.append(b)

    # One-line diagnostic so misses are explainable rather than mysterious.
    # Per-source breakdown of where the hits came from (item 12 added the
    # cascade / SRU / OL paths; surfacing them lets the user see their
    # impact at a glance).
    source_parts: list[str] = []
    if cat_stats.direct_hits:
        source_parts.append(f"{cat_stats.direct_hits} direct LC")
    if cat_stats.cascade_hits:
        source_parts.append(f"{cat_stats.cascade_hits} via OL edition cascade")
    if cat_stats.sru_hits:
        source_parts.append(f"{cat_stats.sru_hits} via LC SRU title+author")
    if cat_stats.ol_hits:
        source_parts.append(f"{cat_stats.ol_hits} via Open Library")
    source_note = f" ({', '.join(source_parts)})" if source_parts else ""
    cat_breakdown = (
        f"[dim]Catalog lookup: {cat_stats.tried_lccn} tried by LCCN, "
        f"{cat_stats.tried_isbn} by ISBN, "
        f"{cat_stats.no_identifiers} had no usable identifier — "
        f"{cat_stats.hits} hit(s){source_note}.[/dim]"
    )
    if catalog_suggestions:
        console.print(
            f"[green]✓[/green] Catalog hits: [bold green]{len(catalog_suggestions)}[/bold green] "
            f"of {len(books)} — AI will only run on the remaining "
            f"[bold]{len(ai_books)}[/bold]."
        )
        console.print(cat_breakdown)
    else:
        console.print(
            f"[dim]No LC catalog hits — falling through to AI for all {len(books)} book(s).[/dim]"
        )
        console.print(cat_breakdown)

    # ── 3b. Pre-fetch publisher descriptions for AI-bound books (item 11) ─────
    # Eliminates lcc_summary hallucination on obscure books by giving the AI
    # an authoritative source to summarise. Graceful degradation: any books
    # without an ISBN, or whose descriptions cannot be fetched, simply do
    # not appear in `description_map` and the AI falls back to its prior
    # training-data behaviour for those rows.
    description_map: dict[int, BookDescription] = {}
    if ai_books:
        isbn_by_book: dict[int, str] = {}
        for b in ai_books:
            ids = db.get_identifiers(b.id)
            isbn = (
                ids.get("isbn")
                or ids.get("isbn13")
                or ids.get("isbn10")
                or ids.get("ISBN")
                or ""
            )
            if isbn:
                isbn_by_book[b.id] = isbn

        if isbn_by_book:
            with console.status(
                f"[cyan]Pre-fetching descriptions for {len(isbn_by_book)} book(s) "
                "(Google Books → Open Library)…[/cyan]"
            ):
                description_map = fetch_descriptions_batch(
                    isbn_by_book,
                    timeout=description_timeout,
                    max_retries=description_max_retries,
                    google_books_api_key=google_books_api_key,
                )
            sources: dict[str, int] = {}
            for d in description_map.values():
                sources[d.source] = sources.get(d.source, 0) + 1
            no_isbn = len(ai_books) - len(isbn_by_book)
            missed = len(isbn_by_book) - len(description_map)
            src_breakdown = ", ".join(
                f"{n} via {name}" for name, n in sorted(sources.items())
            ) or "none"
            console.print(
                f"[dim]Descriptions: {len(description_map)}/{len(ai_books)} fetched "
                f"({src_breakdown}); {missed} no description available; "
                f"{no_isbn} had no ISBN.[/dim]"
            )
        else:
            console.print(
                "[dim]No ISBNs available — skipping description pre-fetch; "
                "AI will fall back to training data.[/dim]"
            )

    # ── 3c. AI lookup for the remainder ───────────────────────────────────────
    ai_suggestions: list[LccSuggestion] = []
    if ai_books:
        with console.status(
            f"[cyan]Querying AI for {len(ai_books)} book(s) "
            f"in batches of {batch_size}…[/cyan]"
        ):
            try:
                ai_suggestions = ai.suggest_lcc(
                    ai_books, current_map, batch_size=batch_size,
                    description_map=description_map,
                )
            except RuntimeError as e:
                console.print(Panel(str(e), title="[red]AI lookup failed[/red]", border_style="red"))
                raise typer.Exit(1)

    suggestions = catalog_suggestions + ai_suggestions

    if not suggestions:
        console.print("[yellow]No suggestions produced (neither catalog nor AI).[/yellow]")
        raise typer.Exit(1)

    # ── 4. Validate ───────────────────────────────────────────────────────────
    validated = [_validate(s) for s in suggestions]

    # Group by confidence
    high = [v for v in validated if v.suggestion.confidence == "high"]
    medium = [v for v in validated if v.suggestion.confidence == "medium"]
    low = [v for v in validated if v.suggestion.confidence == "low"]

    warned = [v for v in validated if v.has_warnings]
    console.print(
        f"\n[bold]Results:[/bold] "
        f"[green]{len(high)} high[/green], "
        f"[yellow]{len(medium)} medium[/yellow], "
        f"[red]{len(low)} low[/red]"
        + (f" — [yellow]{len(warned)} with validation warnings[/yellow]" if warned else "")
        + "\n"
    )

    _LEGEND = (
        "[dim]Legend: [green]●[/green] high (catalog-confirmed)  "
        "[yellow]◐[/yellow] medium (catalog-consensus)  "
        "[red]○[/red] low (schedule-derived or ambiguous)\n"
        "        Pri/Sec shown are CODE-DERIVED from the call number; "
        "warnings flag where AI disagreed.[/dim]\n"
    )

    if high:
        console.print(f"[bold cyan]Tier 1 — High confidence[/bold cyan] [dim]({len(high)})[/dim]")
        console.print(_build_review_table(high))
    if medium:
        console.print(f"\n[bold yellow]Tier 2 — Medium confidence[/bold yellow] [dim]({len(medium)})[/dim]")
        console.print(_build_review_table(medium))
    if low:
        console.print(f"\n[bold red]Tier 3 — Low confidence[/bold red] [dim]({len(low)})[/dim]")
        console.print(_build_review_table(low))
    console.print(_LEGEND)

    # ── 5. Apply (or dry-run) ─────────────────────────────────────────────────
    if dry_run:
        console.print("[bold cyan]── Dry-run: comparing AI proposals to current values ──[/bold cyan]\n")
        console.print(_build_audit_table(validated, current_map))
        _print_audit_summary(validated, current_map)
        return

    applied_ids: list[int] = []
    declined: list[ValidatedSuggestion] = []

    if high:
        if auto_apply_high:
            console.print(f"[bold]--auto-apply-high[/bold]: applying {len(high)} high-confidence enrichments.\n")
            applied_ids += _apply_batch(db, high, columns)
        else:
            choice = Prompt.ask(
                f"\n[bold]Tier 1:[/bold] Apply {len(high)} high-confidence enrichment{'s' if len(high) != 1 else ''}?",
                choices=["all", "review", "skip"], default="all", show_choices=True,
            )
            if choice == "all":
                applied_ids += _apply_batch(db, high, columns)
            elif choice == "review":
                a, d = _prompt_and_apply(db, high, columns)
                applied_ids += a; declined += d

    if medium:
        choice = Prompt.ask(
            f"\n[bold yellow]Tier 2:[/bold yellow] Apply {len(medium)} medium-confidence enrichment{'s' if len(medium) != 1 else ''}?",
            choices=["all", "review", "skip"], default="review", show_choices=True,
        )
        if choice == "all":
            applied_ids += _apply_batch(db, medium, columns)
        elif choice == "review":
            a, d = _prompt_and_apply(db, medium, columns)
            applied_ids += a; declined += d

    if low:
        choice = Prompt.ask(
            f"\n[bold red]Tier 3:[/bold red] Apply {len(low)} low-confidence enrichment{'s' if len(low) != 1 else ''}?",
            choices=["all", "review", "skip"], default="skip", show_choices=True,
        )
        if choice == "all":
            applied_ids += _apply_batch(db, low, columns)
        elif choice == "review":
            a, d = _prompt_and_apply(db, low, columns)
            applied_ids += a; declined += d
        else:
            # Auto-flag skipped low-confidence books for manual curation
            declined += low

    # ── 6. Mark MQG / flag manual ─────────────────────────────────────────────
    # All applied books are marked MQG-03 complete — applied_ids already
    # reflects only what the user explicitly accepted at the review prompt.
    if mqg_column and applied_ids:
        _mark_complete(db, mqg_column, applied_ids, label="MQG-03")

    manual_ids = [v.book_id for v in declined]
    if mqg_manual_column and manual_ids:
        console.print(
            f"\n[yellow]Flagging {len(manual_ids)} book(s)[/yellow] in "
            f"[bold]{mqg_manual_column}[/bold] for manual review."
        )
        with console.status("Flagging…"):
            db.mark_mqg_complete(manual_ids, mqg_manual_column)

    console.print(
        f"\n[bold green]Done![/bold green] "
        f"[green]{len(applied_ids)}[/green] applied, "
        f"[green]{len(applied_ids)}[/green] marked MQG-03 complete"
        + (f", [yellow]{len(manual_ids)}[/yellow] flagged for manual" if manual_ids else "")
        + "."
    )


def _apply_batch(
    db: CalibreDB,
    validated: list[ValidatedSuggestion],
    columns: dict[str, str],
) -> list[int]:
    applied: list[int] = []
    for v in validated:
        with console.status(f"Updating book {v.book_id}…"):
            try:
                _apply_suggestion(db, v, columns)
                applied.append(v.book_id)
            except RuntimeError as e:
                console.print(f"[red]Error on book {v.book_id}: {e}[/red]")
    console.print(f"[green]Applied {len(applied)}/{len(validated)} enrichments.[/green]")
    return applied


def _prompt_and_apply(
    db: CalibreDB,
    validated: list[ValidatedSuggestion],
    columns: dict[str, str],
) -> tuple[list[int], list[ValidatedSuggestion]]:
    to_apply: list[ValidatedSuggestion] = []
    declined: list[ValidatedSuggestion] = []
    for v in validated:
        s = v.suggestion
        console.rule(f"[bold]Book {v.book_id}[/bold]")
        console.print(f"  [bold]{s.title}[/bold]")
        console.print(f"  [dim]{s.authors_display}[/dim]")
        icon, style = _CONF_DISPLAY.get(s.confidence, ("—", "dim"))
        console.print(f"  Confidence: [{style}]{icon} {s.confidence}[/{style}]")
        console.print(
            f"  Source: [bold]{s.attribution_prefix}[/bold] "
            f"[dim italic]{s.source or '(no source text)'}[/dim italic]"
        )
        for field_name in _LCC_FIELDS:
            console.print(f"  [green]→[/green] {field_name}: {v.final_fields[field_name]}")
        if v.has_warnings:
            warns = []
            if v.primary_mismatch:   warns.append("primary mismatch")
            if v.secondary_mismatch: warns.append("secondary mismatch")
            if v.primary_invalid:    warns.append("primary not in canonical list")
            if v.secondary_invalid:  warns.append("secondary not in canonical list")
            console.print(f"  [yellow]Warnings: {'; '.join(warns)}[/yellow]")
        if s.notes:
            console.print(f"  [dim]Note: {s.notes}[/dim]")

        default = "n" if v.has_warnings or s.confidence == "low" else "y"
        choice = Prompt.ask("  Action", choices=["y", "n"], default=default,
                            show_choices=True, show_default=True)
        if choice == "y":
            to_apply.append(v)
        else:
            declined.append(v)
            console.print("  [dim]Declined — will be flagged for manual review.[/dim]")
    applied = _apply_batch(db, to_apply, columns) if to_apply else []
    return applied, declined


def _mark_complete(db: CalibreDB, mqg_column: str, book_ids: list[int], label: str) -> None:
    if not mqg_column or not book_ids:
        return
    with console.status(f"[cyan]Marking {len(book_ids)} books as {label} complete…"):
        db.mark_mqg_complete(book_ids, mqg_column)
    console.print(f"[dim]Marked {len(book_ids)} books complete in [bold]{mqg_column}[/bold].[/dim]")
