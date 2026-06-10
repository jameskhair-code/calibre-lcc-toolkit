"""Tags steps — the three tag flows' dataclasses, prompt assembly, the
post-AI tag-shape enforcer, and response transforms: tags-enrich (batch),
tags-cleanup (vocabulary ops), and tags-review (single book)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from ..db import Book
from ..schemas import (
    SchemaViolation,
    TagCleanupOp,
    TagsItem,
    TagsReviewResponse,
    validate_tag_cleanup,
    validate_tags,
    validate_tags_review,
)
from ._prompts import _load_prompt, _load_rules


@dataclass
class TagOperation:
    source_tags: list[str]
    target_tags: list[str]
    reason: str
    book_count: int = 0
    pattern_group: str = "ai-semantic"

    @property
    def kind(self) -> str:
        if not self.target_tags:
            return "drop"
        if len(self.source_tags) == 1 and len(self.target_tags) == 1:
            return "rename" if self.source_tags[0] != self.target_tags[0] else "noop"
        if len(self.source_tags) > 1 and len(self.target_tags) == 1:
            return "merge"
        if len(self.source_tags) == 1 and len(self.target_tags) > 1:
            return "split"
        return "rewrite"

    @property
    def display_arrow(self) -> str:
        sources = ", ".join(self.source_tags)
        if not self.target_tags:
            return f"{sources} → (drop)"
        if len(self.target_tags) > 1:
            targets = " + ".join(self.target_tags)
        else:
            targets = self.target_tags[0]
        return f"{sources} → {targets}"


@dataclass
class TagsSuggestion:
    book_id: int
    title: str
    authors: list[str]
    current_tags: list[str]
    proposed_tags: list[str]
    confidence: Literal["high", "medium", "low"]
    notes: str = ""
    parse_error: str = ""
    # Cross-step coherence warnings (item 16). Populated by the
    # tags module after the AI returns; surfaced inline during review.
    coherence_warnings: list[str] = field(default_factory=list)

    @property
    def authors_display(self) -> str:
        return " & ".join(self.authors)

    @property
    def tags_changed(self) -> bool:
        return sorted(self.proposed_tags) != sorted(self.current_tags)

    @property
    def kept(self) -> list[str]:
        proposed_lower = {t.lower() for t in self.proposed_tags}
        return [t for t in self.current_tags if t.lower() in proposed_lower]

    @property
    def added(self) -> list[str]:
        current_lower = {t.lower() for t in self.current_tags}
        return [t for t in self.proposed_tags if t.lower() not in current_lower]

    @property
    def removed(self) -> list[str]:
        proposed_lower = {t.lower() for t in self.proposed_tags}
        return [t for t in self.current_tags if t.lower() not in proposed_lower]


@dataclass
class TagsReviewSuggestion:
    book_id: int
    title: str
    authors: list[str]
    current_tags: list[str]
    proposed_tags: list[str]
    assessment: Literal["complete", "needs_additions", "needs_corrections"]
    confidence: Literal["high", "medium", "low"]
    notes: str = ""
    parse_error: str = ""

    @property
    def authors_display(self) -> str:
        return " & ".join(self.authors)

    @property
    def kept(self) -> list[str]:
        proposed_lower = {t.lower() for t in self.proposed_tags}
        return [t for t in self.current_tags if t.lower() in proposed_lower]

    @property
    def added(self) -> list[str]:
        current_lower = {t.lower() for t in self.current_tags}
        return [t for t in self.proposed_tags if t.lower() not in current_lower]

    @property
    def removed(self) -> list[str]:
        proposed_lower = {t.lower() for t in self.proposed_tags}
        return [t for t in self.current_tags if t.lower() not in proposed_lower]


# ── Tags prompt + parsing ─────────────────────────────────────────────────────


def _build_tags_system_prompt() -> str:
    preamble = _load_prompt("tags_preamble.md")
    rules = _load_rules("tags.md")
    output_format = _load_prompt("tags_output_format.md")
    return preamble + "\n" + rules + output_format


def _build_tags_user_message(
    books: list[Book],
    tags_map: dict[int, list[str]],
    context_map: dict[int, dict[str, str]],
    comments_excerpt_map: dict[int, str] | None = None,
) -> str:
    excerpts = comments_excerpt_map or {}
    payload = []
    for b in books:
        item: dict = {"id": b.id, "title": b.title, "authors": b.authors}
        ctx = context_map.get(b.id, {})
        if ctx.get("lcc_primary_class"):
            item["lcc_primary_class"] = ctx["lcc_primary_class"]
        if ctx.get("lcc_secondary_class"):
            item["lcc_secondary_class"] = ctx["lcc_secondary_class"]
        if ctx.get("lcc_summary"):
            item["lcc_summary"] = ctx["lcc_summary"]
        current = tags_map.get(b.id, [])
        if current:
            item["current_tags"] = current
        # Coherence signal from step 04 — see rules/tags.md SCOPE-03
        # for how this fits the evidence priority order.
        excerpt = excerpts.get(b.id, "")
        if excerpt:
            item["existing_comments_excerpt"] = excerpt
        payload.append(item)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_tag_cleanup_system_prompt() -> str:
    return _load_prompt("tag_cleanup_preamble.md") + _load_rules("tags_cleanup.md")


def _build_tag_cleanup_user_message(tags: list[tuple[str, int]]) -> str:
    lines = [f"{name} ({count} book{'s' if count != 1 else ''})" for name, count in tags]
    return "Current tag vocabulary:\n\n" + "\n".join(lines)


def _transform_tag_cleanup_ops(
    raw_ops: list[TagCleanupOp],
    counts: dict[str, int],
) -> list[TagOperation]:
    ops: list[TagOperation] = []
    for raw_op in raw_ops:
        sources = [t.strip() for t in raw_op.source_tags if t.strip()]
        targets = [t.strip() for t in raw_op.target_tags if t.strip()]
        reason = (raw_op.reason or "").strip()
        reason_words = reason.split()
        if len(reason_words) > 10:
            reason = " ".join(reason_words[:10])
        if not sources:
            continue
        if len(sources) == 1 and len(targets) == 1 and sources[0] == targets[0]:
            continue
        total = sum(counts.get(t, 0) for t in sources)
        ops.append(TagOperation(
            source_tags=sources,
            target_tags=targets,
            reason=reason,
            book_count=total,
            pattern_group="ai-semantic",
        ))
    return ops


def _parse_tag_cleanup_response(
    raw: str,
    counts: dict[str, int],
) -> list[TagOperation]:
    return _transform_tag_cleanup_ops(validate_tag_cleanup(raw), counts)


# ── Tags Review prompt + parsing ─────────────────────────────────────────────


def _build_tags_review_system_prompt() -> str:
    return _load_prompt("tags_review_system.md")


def _build_tags_review_user_message(
    book: Book,
    current_tags: list[str],
    description: str,
    series: str,
    year: str,
    publisher: str,
    lcc_summary: str,
    lcc_primary: str,
    lcc_secondary: str,
) -> str:
    item: dict = {"id": book.id, "title": book.title, "authors": book.authors}
    if year:
        item["year"] = year
    if series:
        item["series"] = series
    if publisher:
        item["publisher"] = publisher
    if current_tags:
        item["current_tags"] = current_tags
    if description:
        item["description"] = description[:800]
    if lcc_summary:
        item["lcc_summary"] = lcc_summary
    if lcc_primary:
        item["lcc_primary_class"] = lcc_primary
    if lcc_secondary:
        item["lcc_secondary_class"] = lcc_secondary
    return json.dumps(item, ensure_ascii=False, indent=2)


def _transform_tags_review_item(
    obj: TagsReviewResponse,
    book: Book,
    current_tags: list[str],
) -> TagsReviewSuggestion:
    proposed = [t.strip() for t in obj.proposed_tags if isinstance(t, str) and t.strip()]
    if not proposed:
        proposed = list(current_tags)
    proposed, notes, confidence = _validate_proposed_tags(
        proposed, obj.notes.strip(), obj.confidence,
    )
    return TagsReviewSuggestion(
        book_id=book.id,
        title=book.title,
        authors=book.authors,
        current_tags=list(current_tags),
        proposed_tags=proposed,
        assessment=obj.assessment,
        confidence=confidence,
        notes=notes,
    )


def _parse_tags_review_response(
    raw: str,
    book: Book,
    current_tags: list[str],
) -> TagsReviewSuggestion:
    try:
        obj = validate_tags_review(raw)
    except SchemaViolation as e:
        return TagsReviewSuggestion(
            book_id=book.id, title=book.title, authors=book.authors,
            current_tags=current_tags, proposed_tags=list(current_tags),
            assessment="complete", confidence="low",
            parse_error=str(e)[:200],
        )
    return _transform_tags_review_item(obj, book, current_tags)


_FORM_TAGS = frozenset({
    "Novel", "Short Stories", "Poetry", "Drama", "Memoir",
    "Autobiography", "Biography", "History", "Nonfiction",
    "Essay Collection", "Literary Criticism", "Philosophy",
    "Science", "Political Science", "Journalism",
})


def _validate_proposed_tags(
    proposed: list[str],
    notes: str,
    confidence: str,
) -> tuple[list[str], str, str]:
    """Enforce FORMAT-02 (4-word cap), FORMAT-03 (no commas), FORM-01 (one Form tag)."""
    cleaned = []
    for tag in proposed:
        tag = tag.split(",")[0].strip()  # FORMAT-03: strip at first comma
        words = tag.split()
        if len(words) > 4:              # FORMAT-02: truncate to 4 words
            tag = " ".join(words[:4])
        if tag:
            cleaned.append(tag)

    form_tags = [t for t in cleaned if t in _FORM_TAGS]
    if len(form_tags) != 1:
        confidence = "medium"
        label = ", ".join(form_tags) if form_tags else "none found"
        suffix = f"Form tag issue: {label}."
        notes = f"{notes} {suffix}".strip() if notes else suffix

    return cleaned, notes, confidence


def _transform_tags_items(
    items: list[TagsItem],
    books: list[Book],
    tags_map: dict[int, list[str]],
) -> list[TagsSuggestion]:
    book_map = {b.id: b for b in books}
    suggestions: list[TagsSuggestion] = []
    for item in items:
        book = book_map.get(item.id)
        if book is None:
            continue
        proposed = [t.strip() for t in item.tags if isinstance(t, str) and t.strip()]
        proposed, notes, confidence = _validate_proposed_tags(
            proposed, (item.notes or "").strip(), item.confidence,
        )
        suggestions.append(TagsSuggestion(
            book_id=item.id,
            title=book.title,
            authors=book.authors,
            current_tags=tags_map.get(item.id, []),
            proposed_tags=proposed,
            confidence=confidence,
            notes=notes,
        ))
    return suggestions


def _parse_tags_response(
    raw: str,
    books: list[Book],
    tags_map: dict[int, list[str]],
) -> list[TagsSuggestion]:
    return _transform_tags_items(validate_tags(raw), books, tags_map)
