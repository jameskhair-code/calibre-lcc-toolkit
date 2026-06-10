"""Clean-titles (author/title cleanup) — suggestion dataclass, prompt
assembly, and response transform."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from ..db import Book
from ..normalize import normalize_text, remove_diacritics
from ..schemas import CleanupItem, validate_cleanup
from ._prompts import _load_prompt, _load_rules


def _author_compare_key(name: str) -> str:
    """Normalized key for deciding whether two author strings name the same
    person. Diacritic-, case-, punctuation-, and order-insensitive so that
    legitimate fixes (García → Garcia, "Williams, Joy" → "Joy Williams")
    compare equal and are not mistaken for removals."""
    base = remove_diacritics(name).casefold()
    return " ".join(sorted(re.findall(r"\w+", base)))


@dataclass
class CleanupSuggestion:
    book_id: int
    original_title: str
    original_authors: list[str]
    suggested_title: str
    suggested_authors: list[str]
    confidence: Literal["high", "medium", "low"]
    title_changed: bool
    authors_changed: bool
    notes: str = ""

    @property
    def any_change(self) -> bool:
        return self.title_changed or self.authors_changed

    @property
    def removes_author(self) -> bool:
        """True when an author present in the original has no counterpart in
        the suggestion — a genuine drop or substitution, not a spelling fix.

        Author deletions from model memory are the one clean-titles change
        class that can silently corrupt data, so callers gate this to
        review-only regardless of the AI's stated tier.
        """
        if not self.authors_changed:
            return False
        suggested_keys = {_author_compare_key(a) for a in self.suggested_authors}
        for a in self.original_authors:
            key = _author_compare_key(a)
            if key and key not in suggested_keys:
                return True
        return False

    @property
    def original_authors_display(self) -> str:
        return " & ".join(self.original_authors)

    @property
    def suggested_authors_display(self) -> str:
        return " & ".join(self.suggested_authors)


# ── Prompts ─────────────────────────────────────────────────────────────────
#
# Preambles and output-format blocks live in rules/prompts/*.md alongside the
# step rules, composed at call time so prose edits never require a code
# change. See ROADMAP.md item 10.


def _build_system_prompt(rules_file: str = "author_title.md") -> str:
    preamble = _load_prompt("author_title_preamble.md")
    rules = _load_rules(rules_file)
    output_format = _load_prompt("author_title_output_format.md")
    return preamble + "\n" + rules + "\n" + output_format


def _build_user_message(books: list[Book]) -> str:
    payload = [
        {
            "id": b.id,
            "title": b.title,
            "authors": b.authors,
        }
        for b in books
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _transform_cleanup_items(
    items: list[CleanupItem],
    books: list[Book],
) -> list[CleanupSuggestion]:
    book_map = {b.id: b for b in books}
    suggestions: list[CleanupSuggestion] = []
    for item in items:
        book_id = item.id
        book = book_map.get(book_id)
        if book is None:
            continue

        raw_title = (item.title or book.title).strip()
        raw_authors: list[str] = []
        for a in (item.authors or book.authors):
            if ";" in a:
                raw_authors.extend(x.strip() for x in a.split(";") if x.strip())
            else:
                raw_authors.append(a.strip())

        suggested_title = normalize_text(raw_title)
        suggested_authors = [normalize_text(a) for a in raw_authors]

        ai_changed_title = raw_title != book.title
        ai_changed_authors = raw_authors != book.authors
        code_changed_title = suggested_title != raw_title
        code_changed_authors = any(n != r for n, r in zip(suggested_authors, raw_authors))

        title_changed = suggested_title != book.title
        authors_changed = suggested_authors != book.authors

        notes = item.notes or ""
        _notes_lower = notes.lower().strip(".").strip()
        no_changes_note = _notes_lower in ("no changes needed", "already correctly formatted")

        if (title_changed or authors_changed) and no_changes_note:
            if not ai_changed_title and not ai_changed_authors:
                parts = []
                if code_changed_title:
                    parts.append("title")
                if code_changed_authors:
                    parts.append("authors")
                notes = f"Americanized special characters in {' and '.join(parts)} (diacritics and dashes converted to plain ASCII)."
            else:
                parts = []
                if title_changed:
                    parts.append("title")
                if authors_changed:
                    parts.append("authors")
                notes = f"Corrected {' and '.join(parts)} formatting."

        suggestions.append(CleanupSuggestion(
            book_id=book_id,
            original_title=book.title,
            original_authors=book.authors,
            suggested_title=suggested_title,
            suggested_authors=suggested_authors,
            confidence=item.confidence,
            title_changed=title_changed,
            authors_changed=authors_changed,
            notes=notes,
        ))
    return suggestions


def _parse_response(raw: str, books: list[Book]) -> list[CleanupSuggestion]:
    """Backward-compatible wrapper: validate + transform in one call."""
    return _transform_cleanup_items(validate_cleanup(raw), books)
