"""Tests for item 14 — HTML output validation for comments.

Two layers covered:
  1. The escape() layer in _format_comments_html — AI prose with stray
     `<`, `&`, or even literal `<script>` tags is HTML-escaped before
     being wrapped, so the resulting comments HTML is always benign.
  2. The structural validator in validate_comments_html — catches any
     unexpected tags, attributes, or unbalanced wrappers that slip
     through. Defense in depth against a future change that might
     remove the escape() call.
"""

from __future__ import annotations

from calibre_toolkit.ai import (
    CommentsSuggestion,
    _COMMENTS_SECTION_KEYS,
    _format_comments_html,
    _transform_comments_items,
    validate_comments_html,
)
from calibre_toolkit.db import Book
from calibre_toolkit.schemas import CommentsItem


# ── _format_comments_html escapes AI prose ──────────────────────────────────


class TestFormatCommentsHtmlEscaping:
    def test_plain_text_renders_as_expected_with_wrapper_tags(self):
        sections = {
            "the_book": "A short biography of the founder.",
            "why_read_it": "Concise and well-sourced.",
        }
        out = _format_comments_html(sections, score=8, rationale="Highly recommended.")
        assert "<h3>The Book</h3>" in out
        assert "<p>A short biography of the founder.</p>" in out
        assert "<h3>Must-Read</h3>" in out
        assert "<strong>8 / 10</strong>" in out

    def test_lt_in_ai_text_is_escaped(self):
        sections = {"the_book": "Set in pre-1939 Poland < 100 km from Krakow."}
        out = _format_comments_html(sections)
        assert "&lt;" in out
        # The raw `<` must not appear inside the section body.
        body = out.split("<p>")[1].split("</p>")[0]
        assert "<" not in body

    def test_ampersand_is_escaped(self):
        sections = {"the_book": "Crime & punishment."}
        out = _format_comments_html(sections)
        assert "Crime &amp; punishment." in out

    def test_literal_script_tag_in_ai_text_is_neutralised(self):
        """The original bug: AI returns `<script>` literally. After this
        change, it must land as escaped text, not as live HTML."""
        sections = {"the_book": "Plot summary <script>alert('xss')</script>."}
        out = _format_comments_html(sections)
        assert "<script>" not in out
        assert "&lt;script&gt;" in out
        # The validator should also be happy with this output.
        assert validate_comments_html(out) == []

    def test_double_quote_and_apostrophe_pass_through(self):
        """html.escape with quote=True would escape these, but for body
        text (not attribute values) the default of quote=False is fine.
        Confirming the actual behaviour."""
        sections = {"the_book": 'Title with "quotes" and an apostrophe\'s mark.'}
        out = _format_comments_html(sections)
        # We don't strictly require either, but the assembled HTML must
        # still validate.
        assert validate_comments_html(out) == []

    def test_empty_sections_produce_empty_string(self):
        assert _format_comments_html({}) == ""

    def test_must_read_rationale_is_escaped(self):
        out = _format_comments_html(
            {"the_book": "Body."}, score=7, rationale="Includes <em>strong> opinions",
        )
        assert "&lt;em&gt;" in out


# ── validate_comments_html structural checks ────────────────────────────────


class TestValidateCommentsHtml:
    def test_empty_string_has_no_warnings(self):
        assert validate_comments_html("") == []

    def test_well_formed_assembled_html_passes(self):
        sections = {
            "the_book": "Body text.",
            "why_read_it": "Recommendation prose.",
        }
        out = _format_comments_html(sections, score=8, rationale="Solid.")
        assert validate_comments_html(out) == []

    def test_unknown_tag_is_flagged(self):
        warnings = validate_comments_html("<h3>Title</h3><p>Body</p><div>extra</div>")
        assert any("div" in w for w in warnings)

    def test_script_tag_flagged_even_when_balanced(self):
        warnings = validate_comments_html("<script>alert(1)</script>")
        assert any("script" in w for w in warnings)

    def test_unbalanced_open_tag_flagged(self):
        warnings = validate_comments_html("<h3>Title</h3><p>Body")
        assert any("unclosed" in w for w in warnings)

    def test_unmatched_close_tag_flagged(self):
        warnings = validate_comments_html("</p>")
        assert any("unmatched" in w for w in warnings)

    def test_mismatched_close_tag_flagged(self):
        warnings = validate_comments_html("<h3>Title</p>")
        assert any("mismatched" in w for w in warnings)

    def test_attributes_on_allowed_tag_flagged(self):
        """Our wrapper never emits attributes. If we ever see one, it's
        either a regression in the template or HTML coming from somewhere
        unexpected."""
        warnings = validate_comments_html('<h3 class="hidden">Title</h3>')
        assert any("attributes" in w for w in warnings)

    def test_void_tag_allowed_without_close(self):
        """`<br>` is the canonical void tag — common in editor input. We
        don't emit it but the validator should not complain if it appears."""
        warnings = validate_comments_html("<p>Line one<br>line two</p>")
        assert warnings == []

    def test_self_closing_form_handled(self):
        warnings = validate_comments_html("<p>A<br/>B</p>")
        assert warnings == []


# ── End-to-end through _transform_comments_items ────────────────────────────


def _make_item(book_id: int, **overrides) -> CommentsItem:
    defaults = {
        "id": book_id,
        "book_type": "nonfiction",
        "the_book": "",
        "the_argument": "",
        "the_story": "",
        "what_its_really_about": "",
        "something_you_might_not_know": "",
        "why_read_it": "",
        "must_read_score": 8,
        "must_read_rationale": "Strong.",
        "confidence": "high",
        "notes": "",
    }
    defaults.update(overrides)
    return CommentsItem.model_validate(defaults)


class TestTransformPopulatesHtmlWarnings:
    def test_plain_text_produces_empty_html_warnings(self):
        book = Book(id=1, title="X", authors=["A"])
        item = _make_item(1, the_book="A short well-formed sentence.")
        [s] = _transform_comments_items([item], [book])
        assert s.html_warnings == []

    def test_dangerous_ai_text_is_escaped_so_html_remains_valid(self):
        """AI output containing literal HTML must not produce validator
        warnings — escape() neutralises it before the validator runs."""
        book = Book(id=1, title="X", authors=["A"])
        item = _make_item(1, the_book="Plot <script>alert(1)</script> ends.")
        [s] = _transform_comments_items([item], [book])
        # The HTML must contain the escaped form, not the raw script tag.
        assert "<script>" not in s.html
        assert "&lt;script&gt;" in s.html
        # And the validator should be silent — escape() handled it.
        assert s.html_warnings == []

    def test_html_warnings_field_defaults_to_empty_list(self):
        """A bare CommentsSuggestion (e.g. parse-error fallback) should
        have an empty list, not None, so callers can iterate without a
        guard."""
        s = CommentsSuggestion(
            book_id=1, title="X", authors=["A"], book_type="",
            sections={}, must_read_score=-1, must_read_rationale="",
            html="", confidence="low",
        )
        assert s.html_warnings == []
