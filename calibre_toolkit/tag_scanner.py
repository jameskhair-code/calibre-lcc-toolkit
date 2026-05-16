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
_LCSH_SEPARATOR_RE = re.compile(r"\s+--\s+|\s*;\s+")
_HAS_ALPHA_RE = re.compile(r"[A-Za-z]")


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
    """Drop LCSH chains with 2+ subdivision separators (e.g., -- or ;)."""
    sep_count = len(_LCSH_SEPARATOR_RE.findall(tag))
    if sep_count >= 2:
        return TagOperation(
            source_tags=[tag],
            target_tags=[],
            reason="LCSH chain with multiple subdivisions",
            pattern_group="lcsh-chain",
        )
    return None


def _rule_case_normalize(tag: str, count: int) -> TagOperation | None:
    """Normalize all-lowercase tags to Title Case.

    Conservative: requires 2+ words, alphabetic content only (letters,
    spaces, hyphens, apostrophes). Skips anything with digits, parens,
    or punctuation that suggests a code, fragment, or broken tag.
    Single-word lowercase tags are left alone — too risky (could be
    names, foreign words, BISAC codes, abbreviations).
    """
    stripped = tag.strip()
    if not stripped:
        return None
    words = stripped.split()
    if len(words) < 2 or len(words) > 4:
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
_RULES: list[Callable[[str, int], TagOperation | None]] = [
    _rule_whitespace,
    _rule_lcsh_person_date,    # specific date-prefixed LCSH
    _rule_lcsh_chain,          # multi-subdivision chains
    _rule_date_range_period,   # bare date range → period (before drop)
    _rule_bare_date_range,     # bare date range → drop
    _rule_calibre_taxonomy,    # known taxonomy noise
    _rule_case_normalize,      # last resort: case-only fixes
]


# Human-readable labels for pattern groups in the UI.
PATTERN_GROUP_LABELS: dict[str, str] = {
    "formatting":            "Formatting & whitespace",
    "calibre-taxonomy":      "Calibre taxonomy variants",
    "date-range-lookup":     "Date range → period lookup",
    "lcsh-bare-date-range":  "Bare date ranges (lifespans)",
    "lcsh-date-subject":     "LCSH person/subject headings",
    "lcsh-chain":            "LCSH multi-part chains",
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
