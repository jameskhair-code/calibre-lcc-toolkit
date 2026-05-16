"""
Deterministic tag scanner for cleanup pre-pass.

Applies pattern-based rules to identify high-confidence cleanup operations
(drops, renames) without an AI call. Runs before the AI pass to reduce
the input size and cost.

Each rule is a function (tag, count) -> TagOperation | None.
Rules run in priority order; first match wins.

To add a new rule:
  1. Define a function `_rule_<name>` returning a TagOperation or None
  2. Append it to _RULES in the right priority position
  3. Give it a unique pattern_group string for UI grouping
"""

from __future__ import annotations

import re
from typing import Callable

from .ai import TagOperation


# ── Lookup tables ─────────────────────────────────────────────────────────────

# Known date-range → period name mappings.
# Bare date ranges matching these keys are renamed; ones not in the table
# are treated as person lifespans and dropped.
DATE_RANGE_PERIODS: dict[str, str] = {
    "1939-1945": "World War II",
    "1914-1918": "World War I",
    "1861-1865": "American Civil War",
    "1775-1783": "American Revolution",
    "1865-1877": "Reconstruction",
    "1837-1901": "Victorian Era",
    "1918-1939": "Interwar Period",
    "1945-1991": "Cold War",
    "1789-1799": "French Revolution",
    "1936-1939": "Spanish Civil War",
    "1955-1975": "Vietnam War",
    "1950-1953": "Korean War",
    "1929-1939": "Great Depression",
    "1850-1877": "American Civil War",
    "1607-1776": "Colonial America",
    "1492-1763": "Colonial America",
}

# Calibre-generated taxonomy noise → canonical mapping.
# Lowercased keys for case-insensitive match.
CALIBRE_TAXONOMY: dict[str, str] = {
    # Generic fiction noise → Novel (Form tag)
    "fiction / general": "Novel",
    "fiction - general": "Novel",
    "fiction: general": "Novel",
    "general fiction": "Novel",
    "novels": "Novel",
    # Historical fiction variants
    "fiction / historical": "Historical Fiction",
    "fiction - historical": "Historical Fiction",
    "fiction: historical": "Historical Fiction",
    "fiction.historical": "Historical Fiction",
    "fiction_historical": "Historical Fiction",
    "historical - general": "Historical Fiction",
    "genre: historical fiction": "Historical Fiction",
    # Science fiction variants (NOT sub-genres — those stay distinct)
    "sf": "Science Fiction",
    "sci-fi": "Science Fiction",
    "scifi": "Science Fiction",
    "science-fiction": "Science Fiction",
    "science fiction - general": "Science Fiction",
    "fiction: science fiction": "Science Fiction",
    "fiction - science fiction": "Science Fiction",
    "fiction: science fiction - general": "Science Fiction",
    "fiction / science fiction / general": "Science Fiction",
    "02 science fiction": "Science Fiction",
    # Fantasy variants (NOT sub-genres)
    "fiction / fantasy": "Fantasy",
    "fiction - fantasy": "Fantasy",
    "fiction: fantasy": "Fantasy",
    "fiction: fantasy fiction": "Fantasy",
    "fantasy - general": "Fantasy",
    # Nonfiction variants
    "non-fiction": "Nonfiction",
    "non fiction": "Nonfiction",
    "nonfiction - general": "Nonfiction",
    "non-fiction: history": "History",
    "non-fiction: science": "Science",
    "non-fiction: memoir": "Memoir",
    # WW abbreviations
    "wwii": "World War II",
    "wwi": "World War I",
    "world war (1939-1945)": "World War II",
    "world war (1914-1918)": "World War I",
    # Civil War variants
    "us civil war": "American Civil War",
    "american civil war (1861-1865)": "American Civil War",
    "civil war period (1850-1877)": "American Civil War",
    "civil war era": "American Civil War",
    "civil war history": "American Civil War",
    # Common formatting
    "self help": "Self-Help",
    "post apocalyptic": "Post-Apocalyptic",
    "coming of age": "Coming-of-Age Fiction",
    "coming-of-age": "Coming-of-Age Fiction",
    "magic realism": "Magical Realism",
    "alternative history": "Alternate History",
    "graphic novel": "Graphic Novels",
    # Plurals → singular Form
    "biographies": "Biography",
    "memoirs": "Memoir",
    "personal memoirs": "Memoir",
    "short story collection": "Short Stories",
    "short-stories": "Short Stories",
    "short stories (single author)": "Short Stories",
    "plays": "Drama",
    "theatre": "Drama",
    "theater": "Drama",
    # Goodreads-style geographic literature tags
    "the united states of america": "United States",
}


# ── Compiled patterns ────────────────────────────────────────────────────────

_DATE_RANGE_RE = re.compile(r"^\s*(\d{4})\s*-\s*(\d{4})\b")
_DATE_RANGE_ONLY_RE = re.compile(r"^\s*\d{4}\s*-\s*\d{4}\s*$")
# Covers: double-dash (--), semicolons, em/en dashes (—/–) with or without
# spaces, and space-hyphen-space (older LCSH form "Boston (Mass.) - Fiction").
_LCSH_SEPARATOR_RE = re.compile(r"\s+--\s+|\s*[;—–]\s*|\s+-\s+")
_HAS_ALPHA_RE = re.compile(r"[A-Za-z]")

_TRAILING_NOISE_RE = re.compile(r"[*;.,]+$")
_BISAC_PREFIX_RE = re.compile(r"^[A-Z]{2,}\d{3,}\b")
_FICTION_SLASH_RE = re.compile(r"^Fiction\s*/", re.IGNORECASE)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# No \b: Python \b treats CJK chars as word chars so ".com沉金" wouldn't match
_URL_RE = re.compile(r"://|\.com|\.net|\.org")
_PUBLISHER_YEAR_RE = re.compile(r"\b(?:University\s+Press|University\s+of|Press)\b.{0,60}\b\d{4}\b", re.IGNORECASE)
_LCSH_INITIALS_NAME_RE = re.compile(r"^[A-Z]\.\s+[A-Z]\.\s*\(")
_LCSH_FICTITIOUS_RE = re.compile(r"\((?:Fictitious|Legendary|Mythological|Biblical)\b", re.IGNORECASE)


# ── Rules ────────────────────────────────────────────────────────────────────

def _rule_whitespace(tag: str, count: int) -> TagOperation | None:
    """Strip leading/trailing whitespace."""
    stripped = tag.strip()
    if stripped != tag and stripped:
        return TagOperation(
            source_tags=[tag],
            target_tags=[stripped],
            reason="Trim whitespace",
            pattern_group="formatting",
        )
    return None


def _rule_calibre_taxonomy(tag: str, count: int) -> TagOperation | None:
    """Map known Calibre taxonomy variants to their canonical Form/genre tag."""
    lower = tag.strip().lower()
    if lower not in CALIBRE_TAXONOMY:
        return None
    canonical = CALIBRE_TAXONOMY[lower]
    if canonical == tag:
        return None
    return TagOperation(
        source_tags=[tag],
        target_tags=[canonical],
        reason=f"Calibre taxonomy variant → {canonical}",
        pattern_group="calibre-taxonomy",
    )


def _rule_date_range_period(tag: str, count: int) -> TagOperation | None:
    """Rename bare date ranges to canonical period names via lookup."""
    stripped = tag.strip()
    if not _DATE_RANGE_ONLY_RE.fullmatch(stripped):
        return None
    # Normalize internal whitespace around the dash
    m = _DATE_RANGE_RE.match(stripped)
    if not m:
        return None
    key = f"{m.group(1)}-{m.group(2)}"
    if key in DATE_RANGE_PERIODS:
        return TagOperation(
            source_tags=[tag],
            target_tags=[DATE_RANGE_PERIODS[key]],
            reason=f"Date range maps to known period",
            pattern_group="date-range-lookup",
        )
    return None


def _rule_bare_date_range(tag: str, count: int) -> TagOperation | None:
    """Drop bare date ranges not in the period lookup (person lifespans)."""
    stripped = tag.strip()
    if _DATE_RANGE_ONLY_RE.fullmatch(stripped):
        return TagOperation(
            source_tags=[tag],
            target_tags=[],
            reason="Bare date range (likely person lifespan, not a period)",
            pattern_group="lcsh-bare-date-range",
        )
    return None


def _rule_lcsh_person_date(tag: str, count: int) -> TagOperation | None:
    """Drop LCSH person/subject headings starting with a date range.

    Examples that match:
        1843-1916; Balfour
        1882-1956; Milne
        1869-1954; Artists -- France -- Biography
        1859-1925; Nobility -- Great Britain
        1837-1901 -- Biography
        1837-1901 -- Trials
    """
    stripped = tag.strip()
    m = _DATE_RANGE_RE.match(stripped)
    if not m:
        return None
    remainder = stripped[m.end():].strip()
    if not remainder:
        return None  # handled by bare-date-range rule
    # If remainder starts with a separator, it's an LCSH subject heading
    if remainder.startswith((";", "--", "-")):
        return TagOperation(
            source_tags=[tag],
            target_tags=[],
            reason="LCSH subject heading (date range + subdivision)",
            pattern_group="lcsh-date-subject",
        )
    return None


def _rule_lcsh_chain(tag: str, count: int) -> TagOperation | None:
    """Drop any tag containing an LCSH subdivision separator (-- ; or ' - ')."""
    if _LCSH_SEPARATOR_RE.search(tag):
        return TagOperation(
            source_tags=[tag],
            target_tags=[],
            reason="LCSH subdivision chain",
            pattern_group="lcsh-chain",
        )
    return None


def _rule_case_normalize(tag: str, count: int) -> TagOperation | None:
    """Normalize all-lowercase tags to Title Case.

    Conservative: alphabetic content only (letters, spaces, hyphens,
    apostrophes). Skips anything with digits, parens, or punctuation
    that suggests a code, fragment, or broken tag.
    Single-word tags must be ≥4 chars (avoids short abbreviations).
    Multi-word tags: 2–4 words.
    """
    stripped = tag.strip()
    if not stripped:
        return None
    words = stripped.split()
    if len(words) == 0 or len(words) > 4:
        return None
    if len(words) == 1 and len(stripped) < 4:
        return None
    # All chars must be letters / space / hyphen / apostrophe
    if not all(c.isalpha() or c in " -'" for c in stripped):
        return None
    # Skip if any token contains digits (BISAC codes like FIC019000 etc.)
    if any(any(ch.isdigit() for ch in w) for w in words):
        return None
    if stripped != stripped.lower():
        return None  # only fire on pure all-lowercase
    normalized = _title_case(stripped)
    if normalized == stripped:
        return None
    return TagOperation(
        source_tags=[tag],
        target_tags=[normalized],
        reason="Title Case normalization",
        pattern_group="formatting",
    )


def _rule_trailing_punct(tag: str, count: int) -> TagOperation | None:
    """Strip trailing noise characters (* ; . ,) and rename, or drop if empty.

    If the cleaned result is itself a droppable pattern (BISAC Fiction code,
    BISAC prefix) produce a drop immediately rather than a two-pass rename→drop.
    """
    stripped = tag.strip()
    cleaned = _TRAILING_NOISE_RE.sub("", stripped).strip()
    if not cleaned:
        return TagOperation(
            source_tags=[tag],
            target_tags=[],
            reason="Trailing noise → empty after strip",
            pattern_group="formatting",
        )
    if cleaned != stripped:
        if _FICTION_SLASH_RE.match(cleaned) or _BISAC_PREFIX_RE.match(cleaned):
            return TagOperation(
                source_tags=[tag],
                target_tags=[],
                reason="Trailing noise stripped; result is BISAC code",
                pattern_group="bisac-code",
            )
        return TagOperation(
            source_tags=[tag],
            target_tags=[cleaned],
            reason="Strip trailing noise characters",
            pattern_group="formatting",
        )
    return None


def _rule_garbage_encoding(tag: str, count: int) -> TagOperation | None:
    """Drop tags with control characters, URLs, or predominantly non-ASCII content."""
    stripped = tag.strip()
    if not stripped:
        return None
    if _CONTROL_CHAR_RE.search(stripped):
        return TagOperation(
            source_tags=[tag],
            target_tags=[],
            reason="Contains control characters",
            pattern_group="garbage",
        )
    if _URL_RE.search(stripped):
        return TagOperation(
            source_tags=[tag],
            target_tags=[],
            reason="URL or domain in tag",
            pattern_group="garbage",
        )
    non_ascii = sum(1 for c in stripped if ord(c) > 127)
    if len(stripped) > 3 and non_ascii / len(stripped) > 0.4:
        return TagOperation(
            source_tags=[tag],
            target_tags=[],
            reason="Predominantly non-ASCII / encoding garbage",
            pattern_group="garbage",
        )
    return None


def _rule_bisac_code(tag: str, count: int) -> TagOperation | None:
    """Drop BISAC classification codes (e.g. HIS036140 HISTORY / ...)."""
    if _BISAC_PREFIX_RE.match(tag.strip()):
        return TagOperation(
            source_tags=[tag],
            target_tags=[],
            reason="BISAC classification code",
            pattern_group="bisac-code",
        )
    return None


def _rule_publisher_tag(tag: str, count: int) -> TagOperation | None:
    """Drop publisher-name + year tags (e.g. 'McGill-Queen's University Press 2023')."""
    if _PUBLISHER_YEAR_RE.search(tag):
        return TagOperation(
            source_tags=[tag],
            target_tags=[],
            reason="Publisher name / year tag",
            pattern_group="garbage",
        )
    return None


def _rule_lcsh_initials_name(tag: str, count: int) -> TagOperation | None:
    """Drop LCSH personal name entries in 'A. A. (Full Name)' initials format."""
    if _LCSH_INITIALS_NAME_RE.match(tag.strip()):
        return TagOperation(
            source_tags=[tag],
            target_tags=[],
            reason="LCSH personal name initials entry",
            pattern_group="lcsh-date-subject",
        )
    return None


def _rule_fictitious_character(tag: str, count: int) -> TagOperation | None:
    """Drop LCSH character headings: 'Harry (Fictitious character)', etc."""
    if _LCSH_FICTITIOUS_RE.search(tag):
        return TagOperation(
            source_tags=[tag],
            target_tags=[],
            reason="LCSH fictitious/legendary character heading",
            pattern_group="lcsh-date-subject",
        )
    return None


def _rule_long_phrase(tag: str, count: int) -> TagOperation | None:
    """Drop sentence-length tags (10+ words) — descriptive phrases, not subjects."""
    if len(tag.strip().split()) >= 10:
        return TagOperation(
            source_tags=[tag],
            target_tags=[],
            reason="Sentence-length phrase, not a subject tag",
            pattern_group="garbage",
        )
    return None


def _rule_fiction_bisac(tag: str, count: int) -> TagOperation | None:
    """Drop Fiction/... BISAC taxonomy tags not handled by the taxonomy lookup.

    Must run AFTER _rule_calibre_taxonomy so known mappings (Fiction / Fantasy
    → Fantasy) are applied first. This catches the long tail of unmapped BISAC
    Fiction sub-codes (Fiction / Men's Adventure, Fiction / Absurdist, etc.).
    """
    if _FICTION_SLASH_RE.match(tag.strip()):
        return TagOperation(
            source_tags=[tag],
            target_tags=[],
            reason="Unmapped BISAC Fiction sub-code",
            pattern_group="bisac-code",
        )
    return None


# ── Helpers ──────────────────────────────────────────────────────────────────

_MINOR_WORDS = {"a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "by"}


def _title_case(s: str) -> str:
    """Conservative Title Case: capitalize each significant word."""
    words = s.split()
    result: list[str] = []
    for i, w in enumerate(words):
        if i > 0 and w.lower() in _MINOR_WORDS:
            result.append(w.lower())
        elif w:
            result.append(w[0].upper() + w[1:].lower())
        else:
            result.append(w)
    return " ".join(result)


# ── Rule registry ────────────────────────────────────────────────────────────

# Order matters: more specific rules first, formatting last.
# _rule_fiction_bisac MUST come after _rule_calibre_taxonomy so known
# Fiction/X mappings are applied before the catch-all drop fires.
_RULES: list[Callable[[str, int], TagOperation | None]] = [
    _rule_whitespace,
    _rule_trailing_punct,       # strip trailing * ; . before other rules see the tag
    _rule_garbage_encoding,     # control chars, URLs, non-ASCII garbage
    _rule_long_phrase,          # sentence-length descriptive phrases
    _rule_bisac_code,           # BISAC classification code prefixes
    _rule_publisher_tag,        # publisher name + year noise
    _rule_lcsh_initials_name,   # LCSH "A. A. (Full Name)" person entries
    _rule_fictitious_character, # LCSH "Harry (Fictitious character)" headings
    _rule_lcsh_person_date,     # date-range-prefixed LCSH headings
    _rule_lcsh_chain,           # any single LCSH subdivision separator
    _rule_date_range_period,    # bare date range → period (before drop)
    _rule_bare_date_range,      # bare date range → drop
    _rule_calibre_taxonomy,     # known taxonomy noise
    _rule_fiction_bisac,        # unmapped Fiction/... BISAC codes (after taxonomy)
    _rule_case_normalize,       # last resort: case-only fixes
]


# Human-readable labels for pattern groups in the UI.
PATTERN_GROUP_LABELS: dict[str, str] = {
    "formatting":            "Formatting & whitespace",
    "garbage":               "Garbage / encoding noise",
    "bisac-code":            "BISAC classification codes",
    "calibre-taxonomy":      "Calibre taxonomy variants",
    "date-range-lookup":     "Date range → period lookup",
    "lcsh-bare-date-range":  "Bare date ranges (lifespans)",
    "lcsh-date-subject":     "LCSH person/subject headings",
    "lcsh-chain":            "LCSH subdivision chains",
    "ai-semantic":           "AI semantic analysis",
}


def scan_tags(
    tags: list[tuple[str, int]],
) -> tuple[list[TagOperation], set[str]]:
    """Apply deterministic rules to the full tag list.

    Returns (operations, handled_tags). `handled_tags` is the set of source
    tag names that produced an operation — callers should filter these out
    before sending the remainder to the AI for semantic analysis.
    """
    operations: list[TagOperation] = []
    handled: set[str] = set()
    for tag, count in tags:
        for rule in _RULES:
            op = rule(tag, count)
            if op is None:
                continue
            op.book_count = count
            operations.append(op)
            handled.add(tag)
            break
    return operations, handled
