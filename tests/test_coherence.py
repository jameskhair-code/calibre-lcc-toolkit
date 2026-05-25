"""Unit tests for cross-step coherence checks (roadmap item 16)."""

from __future__ import annotations

from calibre_toolkit.coherence import (
    check_comments_coherence,
    check_tags_coherence,
)


# ── check_comments_coherence ────────────────────────────────────────────────

def test_comments_coherence_passes_when_period_in_prose_and_tags():
    prose = "<p>A vivid account of the Cold War years in Berlin.</p>"
    tags = ["History", "Cold War", "Germany"]
    assert check_comments_coherence(prose, tags) == []


def test_comments_coherence_flags_period_in_prose_but_not_tags():
    prose = "<p>Reframes Cold War history around Soviet interventions.</p>"
    tags = ["History", "20th Century"]  # no Cold War tag
    warnings = check_comments_coherence(prose, tags)
    assert len(warnings) == 1
    assert "Cold War" in warnings[0]


def test_comments_coherence_accepts_spelling_variants():
    prose = "<p>A WWII memoir from the Pacific theatre.</p>"
    tags = ["Memoir", "World War II"]
    assert check_comments_coherence(prose, tags) == []


def test_comments_coherence_handles_html_entities():
    prose = "<h3>The Book</h3><p>The Vietnam War &amp; its aftermath.</p>"
    tags = ["History"]
    warnings = check_comments_coherence(prose, tags)
    assert any("Vietnam War" in w for w in warnings)


def test_comments_coherence_returns_empty_for_empty_prose():
    assert check_comments_coherence("", ["Cold War"]) == []


def test_comments_coherence_word_boundary_avoids_substring_match():
    # "war" should NOT trigger any period — only multi-word phrases match.
    prose = "<p>A treatise on warfare and warden duties.</p>"
    tags = ["Nonfiction"]
    assert check_comments_coherence(prose, tags) == []


def test_comments_coherence_case_insensitive():
    prose = "<p>cold war espionage.</p>"
    tags = ["Thriller"]  # missing period
    warnings = check_comments_coherence(prose, tags)
    assert len(warnings) == 1


def test_comments_coherence_multiple_periods_flagged_separately():
    prose = "<p>Spans the Civil War and Reconstruction era.</p>"
    tags = ["History", "United States"]
    warnings = check_comments_coherence(prose, tags)
    # Both Civil War and Reconstruction should fire.
    assert len(warnings) == 2


# ── check_tags_coherence ────────────────────────────────────────────────────

def test_tags_coherence_passes_when_tag_supported_by_prose():
    tags = ["History", "Cold War"]
    excerpt = "A vivid account of the Cold War in Berlin."
    assert check_tags_coherence(tags, excerpt) == []


def test_tags_coherence_flags_tag_not_supported_by_prose():
    tags = ["History", "Cold War"]
    excerpt = "A Victorian novel about manners and marriage."
    warnings = check_tags_coherence(tags, excerpt)
    assert len(warnings) == 1
    assert "Cold War" in warnings[0]


def test_tags_coherence_returns_empty_when_no_excerpt():
    # No comments yet on the book → no coherence signal to check.
    assert check_tags_coherence(["Cold War"], "") == []


def test_tags_coherence_returns_empty_when_no_tags():
    assert check_tags_coherence([], "Cold War novel.") == []


def test_tags_coherence_handles_html_in_excerpt():
    tags = ["World War II"]
    excerpt = "<h3>The Story</h3><p>A young soldier in WWII Poland.</p>"
    # WWII variant should match World War II tag.
    assert check_tags_coherence(tags, excerpt) == []


def test_tags_coherence_only_flags_period_tags():
    # "Magic Realism" is a subject, not in the period keyword map —
    # the checker is curated to periods so this should NOT warn.
    tags = ["Magic Realism", "Fiction"]
    excerpt = "A novel set in contemporary Mexico City."
    assert check_tags_coherence(tags, excerpt) == []
