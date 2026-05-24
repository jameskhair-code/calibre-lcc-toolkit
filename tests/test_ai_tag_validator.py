"""Tests for ai._validate_proposed_tags — the post-AI tag-shape enforcer."""

from calibre_toolkit.ai import _validate_proposed_tags, _FORM_TAGS


class TestFormatRules:
    def test_truncates_to_four_words(self):
        proposed, _, _ = _validate_proposed_tags(
            ["This Is A Five Word Tag", "Novel"], "", "high",
        )
        # First tag truncated to first four words; Form tag still present.
        assert "This Is A Five" in proposed
        assert "Novel" in proposed

    def test_strips_at_first_comma(self):
        proposed, _, _ = _validate_proposed_tags(
            ["Cold War, Soviet Union", "Novel"], "", "high",
        )
        assert "Cold War" in proposed
        # The "Soviet Union" half is dropped — FORMAT-03 splits on first comma.
        assert "Soviet Union" not in proposed

    def test_drops_empty_after_strip(self):
        proposed, _, _ = _validate_proposed_tags(
            [",", "Novel"], "", "high",
        )
        # The "," tag becomes empty after the comma-strip and is dropped.
        assert proposed == ["Novel"]


class TestFormTagRule:
    def test_exactly_one_form_tag_keeps_high(self):
        proposed, notes, conf = _validate_proposed_tags(
            ["Novel", "Cold War", "United States"], "", "high",
        )
        assert conf == "high"
        assert notes == ""
        assert proposed == ["Novel", "Cold War", "United States"]

    def test_zero_form_tags_downgrades(self):
        _, notes, conf = _validate_proposed_tags(
            ["Cold War", "United States"], "", "high",
        )
        assert conf == "medium"
        assert "none found" in notes.lower()

    def test_multiple_form_tags_downgrades_and_lists(self):
        _, notes, conf = _validate_proposed_tags(
            ["Novel", "Biography", "Cold War"], "", "high",
        )
        assert conf == "medium"
        assert "Novel" in notes
        assert "Biography" in notes

    def test_appends_to_existing_notes(self):
        _, notes, _ = _validate_proposed_tags(
            ["Cold War"], "Existing context.", "high",
        )
        assert notes.startswith("Existing context.")
        assert "Form tag issue" in notes


class TestFormTagRegistry:
    """Guard against accidental removal of canonical Form values."""

    def test_novel_is_form(self):
        assert "Novel" in _FORM_TAGS

    def test_biography_is_form(self):
        assert "Biography" in _FORM_TAGS

    def test_history_is_form(self):
        assert "History" in _FORM_TAGS
