"""Comments enrichment — suggestion dataclass, prompt assembly, the HTML
renderer + structural validator (item 14), and the response transform."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Literal

from ..db import Book, BookDetails
from ..schemas import CommentsItem, validate_comments
from ._prompts import _load_prompt, _load_rules


@dataclass
class CommentsSuggestion:
    book_id: int
    title: str
    authors: list[str]
    book_type: Literal["fiction", "nonfiction", ""]
    sections: dict[str, str]
    must_read_score: int
    must_read_rationale: str
    html: str
    confidence: Literal["high", "medium", "low"]
    notes: str = ""
    parse_error: str = ""
    # Structural HTML warnings from validate_comments_html (item 14).
    # Empty list = well-formed. Non-empty = surfaced during review;
    # the user decides whether to apply.
    html_warnings: list[str] = field(default_factory=list)
    # Cross-step coherence warnings (item 16). Populated by the
    # comments module after the AI returns; surfaced inline during review.
    coherence_warnings: list[str] = field(default_factory=list)

    @property
    def authors_display(self) -> str:
        return " & ".join(self.authors)


# ── Comments prompt + parsing ─────────────────────────────────────────────────

# Prose sections rendered in HTML, in display order. Empty values are skipped,
# so the fiction/non-fiction split is handled implicitly — the AI returns empty
# strings for the keys that do not apply to the book's type.
_COMMENTS_SECTION_KEYS = [
    ("the_book",                     "The Book"),                  # non-fiction
    ("the_story",                    "The Story"),                 # fiction
    ("the_argument",                 "The Argument"),              # non-fiction
    ("what_its_really_about",        "What It's Really About"),    # fiction
    ("something_you_might_not_know", "Something You Might Not Know"),
    ("why_read_it",                  "Why Read It"),
]

def _build_comments_system_prompt() -> str:
    preamble = _load_prompt("comments_preamble.md")
    reader_profile = _load_rules("reader_profile.md")
    comments_rules = _load_rules("comments.md")
    output_format = _load_prompt("comments_output_format.md")

    return (
        preamble
        + "\n\n## READER PROFILE\n\n"
        + reader_profile
        + "\n\n## STRUCTURAL RULES\n\n"
        + comments_rules
        + output_format
    )


def _build_comments_user_message(
    books: list[Book],
    details_map: dict[int, BookDetails],
    lcc_summary_map: dict[int, str] | None = None,
) -> str:
    payload = []
    for b in books:
        d = details_map.get(b.id)
        item: dict = {"id": b.id, "title": b.title, "authors": b.authors}
        if d:
            if d.tags:
                item["tags"] = d.tags
            if d.series:
                item["series"] = d.series
            if d.pubdate:
                item["pubdate"] = d.pubdate
            if d.publisher:
                item["publisher"] = d.publisher
            if d.existing_comments:
                item["existing_comments"] = d.existing_comments[:600]
        if lcc_summary_map:
            lcc_s = lcc_summary_map.get(b.id, "")
            if lcc_s:
                item["lcc_summary"] = lcc_s
        payload.append(item)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _format_comments_html(
    sections: dict[str, str],
    score: int | None = None,
    rationale: str = "",
) -> str:
    """Wrap AI-returned prose in `<h3>`/`<p>` tags for the Calibre comments
    field.

    AI text is HTML-escaped before insertion (item 14). A stray `<` or even
    a `<script>` tag from a misbehaving response now lands as visible text
    (`&lt;script&gt;…`) instead of being interpreted as HTML by Calibre's
    rendering layer. The section labels and our own tag wrappers are
    trusted strings; only the AI-supplied prose is escaped.
    """
    parts = []
    for key, label in _COMMENTS_SECTION_KEYS:
        text = (sections.get(key) or "").strip()
        if not text:
            continue
        parts.append(f"<h3>{html.escape(label)}</h3>\n<p>{html.escape(text)}</p>")
    if score is not None:
        rationale_html = f" — {html.escape(rationale)}" if rationale else ""
        parts.append(
            f"<h3>Must-Read</h3>\n<p><strong>{score} / 10</strong>{rationale_html}</p>"
        )
    return "\n".join(parts)


# ── HTML validation ──────────────────────────────────────────────────────────
#
# Defence in depth: after the AI text is escape()-ed and wrapped, run a
# structural validator over the assembled string. The validator catches
# any tags that slipped through (e.g. if a future refactor removes the
# escape call), unbalanced wrappers (bug in our own template code), or
# disallowed elements (`<script>`, `<iframe>`, etc. should never appear).
#
# A failed validation does not auto-discard the suggestion — the comments
# step surfaces the warning during review so the user can decide. The
# assertion is that *with* escaping, validation should always pass; if it
# starts failing, that's a regression worth seeing.

_ALLOWED_HTML_TAGS: frozenset[str] = frozenset({"h3", "p", "strong"})

# Void elements — no closing tag expected. We don't currently emit any,
# but listing them documents the validator's contract.
_VOID_HTML_TAGS: frozenset[str] = frozenset({"br", "hr", "img"})


class _CommentsHTMLValidator(HTMLParser):
    """Structural validator for our assembled comments HTML.

    Records warnings rather than raising — the caller decides what to do.
    Allow-listed tags pass through cleanly; anything else (including any
    attribute on an otherwise-allowed tag) is flagged. The point isn't to
    sanitise arbitrary HTML — only to verify that our own template plus
    escaped AI text produces exactly the tag shape we expect.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.warnings: list[str] = []
        self._open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID_HTML_TAGS:
            return
        if tag not in _ALLOWED_HTML_TAGS:
            self.warnings.append(
                f"unexpected tag <{tag}> (allowed: {sorted(_ALLOWED_HTML_TAGS)})"
            )
            return
        if attrs:
            attr_names = ", ".join(name for name, _ in attrs)
            self.warnings.append(
                f"<{tag}> carries attributes ({attr_names}); none are expected"
            )
        self._open_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_HTML_TAGS:
            return
        if not self._open_tags:
            self.warnings.append(f"unmatched closing </{tag}> with no open tags")
            return
        expected = self._open_tags.pop()
        if expected != tag:
            self.warnings.append(
                f"mismatched closing </{tag}> (expected </{expected}>)"
            )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Self-closing form (`<br/>`). Treat as a void tag.
        if tag in _VOID_HTML_TAGS:
            return
        self.handle_starttag(tag, attrs)
        if tag in self._open_tags:
            self._open_tags.remove(tag)

    def finish(self) -> list[str]:
        if self._open_tags:
            self.warnings.append(
                f"unclosed tag(s) at end of input: {self._open_tags}"
            )
        return self.warnings


def validate_comments_html(html_text: str) -> list[str]:
    """Return a list of structural-warning strings about the assembled
    comments HTML. An empty list means the HTML is well-formed.

    Defensive: catches any HTMLParser internal error and reports it as a
    single warning rather than propagating. A validator that itself
    crashes must not break the comments pipeline.
    """
    if not html_text:
        return []
    validator = _CommentsHTMLValidator()
    try:
        validator.feed(html_text)
        validator.close()
    except Exception as e:  # pragma: no cover — HTMLParser is robust
        return [f"HTML parser raised {type(e).__name__}: {e}"]
    return validator.finish()


def _coerce_score(value) -> int | None:
    """Best-effort coercion of the AI's score to an int in [0, 10]."""
    if value is None or value == "":
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(10, n))


def _transform_comments_items(
    items: list[CommentsItem],
    books: list[Book],
) -> list[CommentsSuggestion]:
    book_map = {b.id: b for b in books}
    suggestions: list[CommentsSuggestion] = []
    for item in items:
        book = book_map.get(item.id)
        if book is None:
            continue
        section_data = {
            "the_book": item.the_book,
            "the_argument": item.the_argument,
            "the_story": item.the_story,
            "what_its_really_about": item.what_its_really_about,
            "something_you_might_not_know": item.something_you_might_not_know,
            "why_read_it": item.why_read_it,
        }
        sections = {key: (section_data.get(key) or "").strip() for key, _ in _COMMENTS_SECTION_KEYS}
        book_type = item.book_type if item.book_type in ("fiction", "nonfiction") else ""
        score = _coerce_score(item.must_read_score)
        rationale = (item.must_read_rationale or "").strip()
        rendered_html = _format_comments_html(sections, score, rationale)
        suggestions.append(CommentsSuggestion(
            book_id=item.id,
            title=book.title,
            authors=book.authors,
            book_type=book_type,
            sections=sections,
            must_read_score=score if score is not None else -1,
            must_read_rationale=rationale,
            html=rendered_html,
            confidence=item.confidence,
            notes=(item.notes or "").strip(),
            html_warnings=validate_comments_html(rendered_html),
        ))
    return suggestions


def _parse_comments_response(raw: str, books: list[Book]) -> list[CommentsSuggestion]:
    return _transform_comments_items(validate_comments(raw), books)
