"""
MQG-02 Identifier Enrichment — pure domain helpers.

Title-match classification, the suggestion dataclass, the parallel lookup
pool, and the review-table builder. The enrich-identifiers orchestration
lives in `commands/enrich_identifiers.py`; unflag-manual lives in
`commands/unflag_manual.py`.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text
from rich import box

from ..db import Book
from ..fetcher import IdentifierFetcher, IDENTIFIER_TYPES
from ..logging_config import get_logger

_log = get_logger(__name__)


console = Console()

# ── Title match classification ────────────────────────────────────────────────

# Suffixes that are generic publication noise — same book, different marketing copy
_GENERIC_SUBTITLE_RE = re.compile(
    r":\s*(a|an|the)\s+"
    r"(novel|memoir|story|thriller|mystery|romance|biography|history|narrative|"
    r"tale|journey|collection|stories|poems|play|drama|comedy|novella|account|"
    r"chronicle|true\s+story|life|portrait)\s*$",
    re.IGNORECASE,
)

# Book club branding — typically a different print run / ISBN, not the original edition
_BOOK_CLUB_RE = re.compile(
    r"\b(oprah|reese|gma|book\s*club)\b"
    r"|\(.*book\s+club.*\)",
    re.IGNORECASE,
)

# Tie-in / adapted editions — not the original trade edition
_TIE_IN_RE = re.compile(
    r"\b(movie|film|tv|television|screen)\s*(tie[-\s]in|edition|version|adaptation)\b"
    r"|\(movie\s+tie[-\s]?in\)|\(film\s+tie[-\s]?in\)",
    re.IGNORECASE,
)


def _classify_title_match(calibre_title: str, returned_title: str) -> str:
    """Classify how the returned title relates to the Calibre title.

    Returns one of:
      "match"            — effectively the same title
      "generic_subtitle" — returned adds only generic publication noise (': A Novel')
      "book_club"        — returned has book club branding (likely different ISBN)
      "tie_in"           — returned has tie-in/movie marker (likely different ISBN)
      "mismatch"         — other meaningful difference — verify edition
    """
    if not returned_title:
        return "match"

    cal = calibre_title.strip()
    ret = returned_title.strip()

    if cal.lower() == ret.lower():
        return "match"

    # Check for specific edition flags before anything else
    if _BOOK_CLUB_RE.search(ret):
        return "book_club"
    if _TIE_IN_RE.search(ret):
        return "tie_in"

    # Strip generic subtitle from returned title and re-compare
    ret_stripped = _GENERIC_SUBTITLE_RE.sub("", ret).strip()
    if cal.lower() == ret_stripped.lower():
        return "generic_subtitle"

    # Calibre title is a clean prefix of the returned title (subtitle added)
    if ret_stripped.lower().startswith(cal.lower() + ":") or ret_stripped.lower() == cal.lower():
        return "generic_subtitle"

    return "mismatch"


# Labels and styles for each match class
_MATCH_CLASS_DISPLAY = {
    "match":            ("↳ matches",               "dim green",  ""),
    "generic_subtitle": ("↳ subtitle noise only",   "dim green",  ""),
    "book_club":        ("↳ book club edition",      "red",        " — likely different ISBN"),
    "tie_in":           ("↳ tie-in edition",         "red",        " — likely different ISBN"),
    "mismatch":         ("↳ title differs",          "yellow",     " — verify edition"),
}


@dataclass
class IdentifierSuggestion:
    book_id: int
    title: str
    authors: list[str]
    current_identifiers: dict[str, str]
    found_identifiers: dict[str, str]
    new_identifiers: dict[str, str]        # found - current
    lookup_method: str                     # "isbn" | "title_author"
    confidence: str                        # "high" | "low"
    lookup_attempted: bool
    lookup_error: str | None = None
    already_sufficient: bool = False
    returned_title: str = ""              # title returned by the lookup service
    returned_authors: list[str] = field(default_factory=list)

    @property
    def any_new(self) -> bool:
        return bool(self.new_identifiers)

    @property
    def author_display(self) -> str:
        return " & ".join(self.authors)

    @property
    def title_match_class(self) -> str:
        return _classify_title_match(self.title, self.returned_title)

    @property
    def returned_title_differs(self) -> bool:
        return self.title_match_class not in ("match", "generic_subtitle")


def _is_sufficient(identifiers: dict[str, str], required: list[str]) -> bool:
    """True only when ALL required types are present — ensures multirun enrichment."""
    return all(t in identifiers for t in required)


def _confidence_style(confidence: str) -> tuple[str, str]:
    return {"high": ("●", "green"), "low": ("○", "red")}.get(confidence, ("—", "dim"))


def _ids_display(identifiers: dict[str, str], highlight_keys: set[str] | None = None) -> Text:
    t = Text()
    for i, (k, v) in enumerate(identifiers.items()):
        if i:
            t.append("  ")
        style = "green bold" if highlight_keys and k in highlight_keys else "dim"
        t.append(f"{k}:", style="dim")
        t.append(v, style=style)
    return t


def _build_review_table(
    suggestions: list[IdentifierSuggestion],
    show_returned_title: bool = False,
) -> Table:
    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4, no_wrap=True)
    table.add_column("Conf", width=5, no_wrap=True)
    table.add_column("Book", ratio=4)
    table.add_column("Current IDs", ratio=3)
    table.add_column("New IDs Found", ratio=4)
    table.add_column("Method", width=13, no_wrap=True)

    for i, s in enumerate(suggestions, 1):
        icon, style = _confidence_style(s.confidence)
        conf_text = Text(icon, style=style)

        book_text = Text()
        book_text.append(s.title)
        book_text.append(f"\n{s.author_display}", style="dim")
        if show_returned_title and s.returned_title:
            mc = s.title_match_class
            label, style, note = _MATCH_CLASS_DISPLAY[mc]
            if mc in ("match", "generic_subtitle"):
                book_text.append(f"\n{label}", style=style)
            else:
                book_text.append(f"\n{label}: ", style=style)
                book_text.append(s.returned_title, style=f"{style} italic")
                if note:
                    book_text.append(note, style=f"{style} bold")

        current_text = Text()
        if s.current_identifiers:
            current_text.append("  ".join(s.current_identifiers.keys()), style="dim")
        else:
            current_text.append("(none)", style="dim italic")

        if s.lookup_error:
            new_text = Text(f"[{s.lookup_error}]", style="dim italic")
            method_text = Text("—", style="dim")
        else:
            new_text = _ids_display(s.new_identifiers, highlight_keys=set(s.new_identifiers))
            if not s.new_identifiers:
                new_text = Text("(nothing new)", style="dim italic")
            method_text = Text(s.lookup_method.replace("_", "/"), style="dim")

        table.add_row(str(i), conf_text, book_text, current_text, new_text, method_text)

    return table


def _parallel_lookup(
    fetcher: IdentifierFetcher,
    pending: list[tuple[Book, dict[str, str]]],
    max_workers: int,
) -> dict[int, "IdentifierSuggestion"]:
    """Run fetcher.fetch for each (book, current_ids) pair concurrently.

    Returns a {book_id: IdentifierSuggestion} map; the caller stitches these
    into the final list in input order so the review table is deterministic.

    `subprocess.run` releases the GIL during the wait, so threading gives real
    concurrency for the I/O-bound lookups. A single Rich progress bar keeps
    output coherent across worker threads — per-worker `console.status()`
    would interleave illegibly.
    """
    results: dict[int, IdentifierSuggestion] = {}
    if not pending:
        return results

    workers = max(1, min(max_workers, len(pending)))

    def _lookup_one(book: Book, current: dict[str, str]) -> IdentifierSuggestion:
        isbn = current.get("isbn")
        try:
            result = fetcher.fetch(isbn=isbn, title=book.title, authors=book.authors)
        except Exception as exc:  # last-resort safety net
            _log.exception("identifier lookup raised for book %d", book.id)
            return IdentifierSuggestion(
                book_id=book.id,
                title=book.title,
                authors=book.authors,
                current_identifiers=current,
                found_identifiers={},
                new_identifiers={},
                lookup_method="",
                confidence="low",
                lookup_attempted=True,
                lookup_error=f"unexpected: {exc!r}"[:200],
                already_sufficient=False,
            )

        new_ids = {k: v for k, v in result.identifiers.items() if k not in current}
        return IdentifierSuggestion(
            book_id=book.id,
            title=book.title,
            authors=book.authors,
            current_identifiers=current,
            found_identifiers=result.identifiers,
            new_identifiers=new_ids,
            lookup_method=result.lookup_method,
            confidence=result.confidence,
            lookup_attempted=True,
            lookup_error=result.error,
            already_sufficient=False,
            returned_title=result.title,
            returned_authors=result.authors,
        )

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[cyan]Looking up identifiers"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )
    with progress:
        task = progress.add_task("lookup", total=len(pending))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_lookup_one, book, current): book.id
                for book, current in pending
            }
            for fut in as_completed(futures):
                bid = futures[fut]
                results[bid] = fut.result()
                progress.advance(task)

    return results
