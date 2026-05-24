"""Tests for normalize.normalize_text and its component helpers."""

import pytest

from calibre_toolkit.normalize import (
    normalize_dashes,
    normalize_text,
    remove_diacritics,
)


class TestRemoveDiacritics:
    @pytest.mark.parametrize("inp,want", [
        ("café", "cafe"),
        ("Müller", "Muller"),
        ("naïve", "naive"),
        ("Adichie", "Adichie"),     # no-op
        ("Ångström", "Angstrom"),
    ])
    def test_strips_combining_marks(self, inp, want):
        assert remove_diacritics(inp) == want

    @pytest.mark.parametrize("inp,want", [
        ("Straße", "Strasse"),
        ("Encyclopædia", "Encyclopaedia"),
        ("cœur", "coeur"),
        ("Łódź", "Lodz"),
    ])
    def test_special_letter_map(self, inp, want):
        assert remove_diacritics(inp) == want


class TestNormaliseDashes:
    @pytest.mark.parametrize("inp,want", [
        ("a — b", "a - b"),
        ("a – b", "a - b"),
        ("a − b", "a - b"),
        ("plain - hyphen", "plain - hyphen"),
    ])
    def test_dashes_become_hyphen(self, inp, want):
        assert normalize_dashes(inp) == want


class TestNormalizeTextPipeline:
    def test_dashes_and_diacritics(self):
        assert normalize_text("Café — Müller") == "Cafe - Muller"

    def test_empty(self):
        assert normalize_text("") == ""
