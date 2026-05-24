"""Tests for the deterministic tag scanner.

Each rule has a representative happy-path case and at least one negative
case so we catch over-eager matching. The top-level `scan_tags` is tested
end-to-end to lock in rule priority ordering.
"""

import pytest

from calibre_toolkit.tag_scanner import (
    DATE_RANGE_PERIODS,
    _title_case,
    scan_tags,
)


def _scan_one(tag: str, count: int = 1):
    """Run scan_tags on a single tag and return the operation (or None)."""
    ops, handled = scan_tags([(tag, count)])
    return ops[0] if ops else None


class TestWhitespace:
    def test_strips_outer_whitespace(self):
        op = _scan_one("  Novel  ")
        assert op is not None
        assert op.target_tags == ["Novel"]
        assert op.pattern_group == "formatting"


class TestCalibreTaxonomy:
    def test_maps_known_variant(self):
        op = _scan_one("Fiction / Historical")
        assert op is not None
        assert op.target_tags == ["Historical Fiction"]
        assert op.pattern_group == "calibre-taxonomy"

    def test_case_insensitive_match(self):
        op = _scan_one("SCI-FI")
        assert op is not None
        assert op.target_tags == ["Science Fiction"]

    def test_noop_when_canonical_already(self):
        # 'Novel' is the canonical Form tag; the scanner shouldn't fire.
        assert _scan_one("Novel") is None


class TestDateRangePeriod:
    def test_known_date_range_renamed_to_period(self):
        op = _scan_one("1939-1945")
        assert op is not None
        assert op.target_tags == ["World War II"]
        assert op.pattern_group == "date-range-lookup"

    def test_unknown_date_range_dropped_as_lifespan(self):
        op = _scan_one("1843-1916")
        assert op is not None
        assert op.target_tags == []  # drop
        assert op.pattern_group == "lcsh-bare-date-range"

    def test_period_table_keys_resolve(self):
        """Every entry in DATE_RANGE_PERIODS should resolve via the period rule."""
        for key in DATE_RANGE_PERIODS:
            op = _scan_one(key)
            assert op is not None, f"{key} did not produce a rule match"
            assert op.target_tags == [DATE_RANGE_PERIODS[key]], (
                f"{key} mapped to {op.target_tags} not {DATE_RANGE_PERIODS[key]}"
            )


class TestLcshChains:
    def test_double_dash_separator_dropped(self):
        op = _scan_one("United States -- History -- 20th century")
        assert op is not None
        assert op.target_tags == []
        assert op.pattern_group == "lcsh-chain"

    def test_em_dash_separator_dropped(self):
        op = _scan_one("World War, 1939-1945—Campaigns")
        assert op is not None
        assert op.target_tags == []

    def test_person_date_with_subdivision_dropped(self):
        op = _scan_one("1843-1916; Balfour")
        assert op is not None
        assert op.target_tags == []
        assert op.pattern_group == "lcsh-date-subject"


class TestGarbage:
    def test_url_dropped(self):
        op = _scan_one("see https://example.com")
        assert op is not None
        assert op.target_tags == []
        assert op.pattern_group == "garbage"

    def test_control_char_dropped(self):
        op = _scan_one("bad\x00tag")
        assert op is not None
        assert op.target_tags == []

    def test_sentence_length_dropped(self):
        op = _scan_one("this is a description that should not be a tag at all")
        assert op is not None
        assert op.target_tags == []

    def test_bisac_code_dropped(self):
        op = _scan_one("HIS036140 HISTORY / Military / World War II")
        assert op is not None
        assert op.target_tags == []
        assert op.pattern_group == "bisac-code"


class TestCaseNormalize:
    def test_lowercase_two_word_titlecased(self):
        op = _scan_one("cold war")
        assert op is not None
        assert op.target_tags == ["Cold War"]

    def test_already_titlecased_noop(self):
        assert _scan_one("Cold War") is None

    def test_minor_word_stays_lowercase(self):
        op = _scan_one("history of the world")
        assert op is not None
        assert op.target_tags == ["History of the World"]

    def test_short_single_word_skipped(self):
        # <4 chars => skipped to avoid breaking abbreviations like "fbi"
        assert _scan_one("fbi") is None

    def test_with_digits_skipped(self):
        # digits suggest a code, not a normal tag
        assert _scan_one("history 101") is None


class TestTrailingPunctuation:
    def test_trailing_semicolon_stripped(self):
        op = _scan_one("Novel;")
        assert op is not None
        assert op.target_tags == ["Novel"]

    def test_abbreviation_dot_preserved(self):
        # "Franklin D." should NOT have the dot stripped
        assert _scan_one("Franklin D.") is None


class TestGeographicQualifier:
    def test_strips_state_qualifier(self):
        op = _scan_one("Boston (Mass.)")
        assert op is not None
        assert op.target_tags == ["Boston"]


class TestLocationPrefix:
    def test_strips_location_prefix(self):
        op = _scan_one("Location: New York City")
        assert op is not None
        assert op.target_tags == ["New York City"]


class TestScanTagsTopLevel:
    def test_returns_handled_set(self):
        tags = [
            ("Novel", 100),
            ("  Novel  ", 1),
            ("Fiction / Historical", 5),
            ("Some Clean Tag", 10),
        ]
        ops, handled = scan_tags(tags)
        # "Novel" canonical, "Some Clean Tag" already-cased, should NOT be handled
        assert "Novel" not in handled
        assert "Some Clean Tag" not in handled
        # The dirty ones SHOULD be handled
        assert "  Novel  " in handled
        assert "Fiction / Historical" in handled
        assert len(ops) == len(handled)

    def test_book_count_propagated(self):
        ops, _ = scan_tags([("Fiction / Historical", 42)])
        assert ops[0].book_count == 42

    def test_priority_taxonomy_beats_fiction_bisac(self):
        # 'Fiction / Fantasy' is in the taxonomy lookup → mapped to Fantasy.
        # Without correct priority it would fall through to the BISAC drop.
        op = _scan_one("Fiction / Fantasy")
        assert op is not None
        assert op.target_tags == ["Fantasy"], (
            "calibre-taxonomy must run before the fiction-bisac catch-all drop"
        )


class TestTitleCaseHelper:
    @pytest.mark.parametrize("inp,want", [
        ("cold war", "Cold War"),
        ("history of the world", "History of the World"),
        ("the great gatsby", "The Great Gatsby"),
        ("", ""),
    ])
    def test_title_case(self, inp, want):
        assert _title_case(inp) == want
