"""Tests for the scope filter in tags-cleanup (roadmap item 18).

The filter itself is a pure function over (TagOperation, set[str]),
which is what these tests exercise. The full run_tags_cleanup
orchestration is interactive and covered by hand-driven smoke tests
on a real library.
"""

from __future__ import annotations

from calibre_toolkit.ai import TagOperation
from calibre_toolkit.modules.tags import _op_touches_scope


def _op(*, source_tags: list[str], target_tags: list[str] | None = None) -> TagOperation:
    return TagOperation(
        source_tags=source_tags,
        target_tags=target_tags or [],
        reason="test",
        book_count=1,
        pattern_group="ai-semantic",
    )


def test_op_in_scope_when_single_source_tag_matches():
    op = _op(source_tags=["Fiction"], target_tags=["Novel"])
    assert _op_touches_scope(op, {"Fiction", "History"}) is True


def test_op_out_of_scope_when_no_source_tag_matches():
    op = _op(source_tags=["Memoir"], target_tags=["Autobiography"])
    assert _op_touches_scope(op, {"Fiction", "History"}) is False


def test_op_in_scope_when_any_source_tag_matches():
    # Merge ops can have multiple source tags — match on any of them.
    op = _op(source_tags=["sci-fi", "scifi", "Science Fiction"],
             target_tags=["Science Fiction"])
    assert _op_touches_scope(op, {"Science Fiction"}) is True


def test_op_out_of_scope_when_scope_is_empty():
    op = _op(source_tags=["Fiction"])
    assert _op_touches_scope(op, set()) is False


def test_match_is_case_sensitive_by_design():
    # Calibre stores tag names case-sensitively. A case-insensitive
    # compare would over-match — e.g. lowercase 'fiction' on a scope
    # book picking up an op that targets the canonical 'Fiction'.
    op = _op(source_tags=["Fiction"])
    assert _op_touches_scope(op, {"fiction"}) is False
    assert _op_touches_scope(op, {"Fiction"}) is True


def test_drop_op_with_no_target_tags_still_evaluated_on_source():
    # Drop ops have an empty target_tags list; the filter only looks at
    # source_tags so this should behave the same as a rename or merge.
    op = _op(source_tags=["Goodreads-Shelf"], target_tags=[])
    assert _op_touches_scope(op, {"Goodreads-Shelf"}) is True
    assert _op_touches_scope(op, {"Fiction"}) is False
