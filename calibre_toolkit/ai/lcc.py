"""LCC enrichment — suggestion dataclass, source-authority contract, prompt
assembly, and response transforms (the main lcc call and the v1.7 item-5
summary-only call)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ..db import Book
from ..schemas import LccItem, validate_lcc
from ._prompts import _load_prompt, _load_rules

if TYPE_CHECKING:
    from ..services.book_description import BookDescription


SourceAuthority = Literal[
    "lc_catalog",
    "worldcat_consensus",
    "open_library",
    "ai_inference",
]

_SOURCE_AUTHORITY_VALUES: frozenset[str] = frozenset({
    "lc_catalog", "worldcat_consensus", "open_library", "ai_inference",
})

_ATTRIBUTION_PREFIX = {
    "lc_catalog":         "[LC]",
    "worldcat_consensus": "[WC]",
    "open_library":       "[OL]",
    "ai_inference":       "[AI]",
}


@dataclass
class LccSuggestion:
    book_id: int
    title: str
    authors: list[str]
    current: dict[str, str]
    proposed: dict[str, str]
    confidence: Literal["high", "medium", "low"]
    source: str = ""
    notes: str = ""
    parse_error: str = ""
    # Structural provenance. The AI returns it as a hint; the parser
    # downgrades any unsupported claim to "ai_inference" (see
    # _normalise_lcc_source_authority). Catalog-built suggestions
    # populate this directly in _build_catalog_suggestion.
    source_authority: SourceAuthority = "ai_inference"

    @property
    def authors_display(self) -> str:
        return " & ".join(self.authors)

    @property
    def any_change(self) -> bool:
        return any(
            self.proposed.get(k, "") != self.current.get(k, "")
            for k in ("lcc", "lcc_primary_class", "lcc_secondary_class", "lcc_summary")
        )

    @property
    def attribution_prefix(self) -> str:
        """Display prefix derived purely from source_authority — never from
        the AI's free-text source string. Reviewers and the audit log can
        rely on this to distinguish AI-only rows from catalog-confirmed ones.
        """
        return _ATTRIBUTION_PREFIX.get(self.source_authority, "[AI]")


# ── LCC prompt + parsing ─────────────────────────────────────────────────────


def _build_lcc_system_prompt() -> str:
    preamble = _load_prompt("lcc_preamble.md")
    rules = _load_rules("lcc.md")
    output_format = _load_prompt("lcc_output_format.md")
    return preamble + "\n" + rules + "\n" + output_format


def _build_lcc_user_message(
    books: list[Book],
    current_map: dict[int, dict[str, str]],
    description_map: dict[int, "BookDescription"] | None = None,
) -> str:
    description_map = description_map or {}
    payload = []
    for b in books:
        current = current_map.get(b.id, {})
        item: dict = {
            "id": b.id,
            "title": b.title,
            "authors": b.authors,
        }
        if any(current.get(k) for k in ("lcc", "lcc_primary_class", "lcc_secondary_class", "lcc_summary")):
            item["current"] = {k: current.get(k, "") for k in
                               ("lcc", "lcc_primary_class", "lcc_secondary_class", "lcc_summary")}
        # Pre-fetched description (item 11). When present, the prompt
        # instructs the model to summarise from it instead of training data.
        desc = description_map.get(b.id)
        if desc is not None and desc.text:
            item["description"] = desc.text
            item["description_source"] = desc.source
            if desc.categories:
                item["description_categories"] = desc.categories
        payload.append(item)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _normalise_lcc_source_authority(
    raw_value: object,
    notes: str,
) -> tuple[SourceAuthority, str]:
    """Enforce the source_authority contract documented in SRC-06.

    The AI is called only after direct catalog lookups have already missed,
    so any `lc_catalog` or `worldcat_consensus` claim it returns cannot be
    structurally verified by us and is downgraded to `ai_inference` with a
    visible note appended.

    Returns (normalised_authority, normalised_notes).
    """
    value = (str(raw_value) if raw_value is not None else "").strip().lower()
    if value not in _SOURCE_AUTHORITY_VALUES:
        return "ai_inference", notes

    if value in ("lc_catalog", "worldcat_consensus"):
        suffix = (
            f"AI claimed source_authority={value!r} but no catalog hit was "
            "passed in; downgraded to ai_inference."
        )
        new_notes = f"{notes} {suffix}".strip() if notes else suffix
        return "ai_inference", new_notes

    # open_library and ai_inference pass through as-is.
    return value, notes  # type: ignore[return-value]


def _transform_lcc_items(
    items: list[LccItem],
    books: list[Book],
    current_map: dict[int, dict[str, str]],
) -> list[LccSuggestion]:
    book_map = {b.id: b for b in books}
    suggestions: list[LccSuggestion] = []
    for item in items:
        book = book_map.get(item.id)
        if book is None:
            continue
        proposed = {
            "lcc": item.lcc.strip(),
            "lcc_primary_class": item.lcc_primary_class.strip(),
            "lcc_secondary_class": item.lcc_secondary_class.strip(),
            "lcc_summary": item.lcc_summary.strip(),
        }
        notes = item.notes.strip()
        authority, notes = _normalise_lcc_source_authority(
            item.source_authority, notes,
        )
        suggestions.append(LccSuggestion(
            book_id=item.id,
            title=book.title,
            authors=book.authors,
            current=current_map.get(item.id, {}),
            proposed=proposed,
            confidence=item.confidence,
            source=item.source.strip(),
            notes=notes,
            source_authority=authority,
        ))
    return suggestions


def _parse_lcc_response(
    raw: str,
    books: list[Book],
    current_map: dict[int, dict[str, str]],
) -> list[LccSuggestion]:
    return _transform_lcc_items(validate_lcc(raw), books, current_map)


# ── LCC summary-only prompt + parsing (v1.7 item 5) ──────────────────────────


def _build_lcc_summary_system_prompt() -> str:
    preamble = _load_prompt("lcc_summary_preamble.md")
    rules = _load_rules("lcc_summary.md")
    output_format = _load_prompt("lcc_summary_output_format.md")
    return preamble + "\n" + rules + "\n" + output_format


def _build_lcc_summary_user_message(
    books: list[Book],
    catalog_context_map: dict[int, dict[str, str]],
    description_map: dict[int, "BookDescription"],
) -> str:
    payload = []
    for b in books:
        ctx = catalog_context_map.get(b.id, {})
        item: dict = {
            "id": b.id,
            "title": b.title,
            "authors": b.authors,
            "lcc": ctx.get("lcc", ""),
            "lcc_primary_class": ctx.get("lcc_primary_class", ""),
            "lcc_secondary_class": ctx.get("lcc_secondary_class", ""),
            "catalog_source": ctx.get("catalog_source", ""),
        }
        desc = description_map.get(b.id)
        if desc is not None and desc.text:
            item["description"] = desc.text
            item["description_source"] = desc.source
            if desc.categories:
                item["description_categories"] = desc.categories
        payload.append(item)
    return json.dumps(payload, ensure_ascii=False, indent=2)
