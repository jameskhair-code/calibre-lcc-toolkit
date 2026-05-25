"""Tests for v1.3 item 15 — Unicode and encoding robustness.

Two surfaces covered:

  1. normalize.normalize_text — confirms the script-aware behaviour
     introduced for item 15: Latin diacritics still strip; non-Latin
     scripts (Cyrillic, Greek, Arabic, Hebrew, CJK, emoji) pass through
     intact, including combining marks that are letter-distinguishing
     in their script (Cyrillic Й vs И, Greek polytonic, Arabic vowels).

  2. db._sanitize_identifier — confirms the calibredb identifier-string
     escaping rules: empty / control / forbidden-character / wrong-key
     entries are dropped, valid ones round-trip with whitespace stripped
     and the key lowercased.

These exercise the silent-data-loss surfaces flagged in the roadmap.
Before item 15, normalize_text was rewriting Достоевский ('Dostoevsky')
to Достоевскии — turning a Russian word into a different non-word —
and db.apply_identifiers was filtering ',' from values but not ':'
despite its docstring claiming otherwise.
"""

from __future__ import annotations

import pytest

from calibre_toolkit.normalize import normalize_text, remove_diacritics
from calibre_toolkit.db import _sanitize_identifier


# ── Cyrillic: combining marks are LETTER-DISTINGUISHING ─────────────────────


class TestCyrillicPreserved:
    """Й (short-i) is a distinct letter from И in Russian. The previous
    NFKD-then-strip-combining logic silently demoted Й → И, turning
    Russian names into different words."""

    def test_dostoyevsky_preserved(self):
        # Достоевский — Russian author's surname with terminal Й.
        assert normalize_text("Достоевский") == "Достоевский"

    def test_tolstoy_preserved(self):
        # Толстой ends in Й.
        assert normalize_text("Толстой") == "Толстой"

    def test_tsoi_preserved(self):
        # Виктор Цой — Russian musician, very common surname pattern.
        assert normalize_text("Виктор Цой") == "Виктор Цой"

    def test_ukrainian_short_u_preserved(self):
        # Belarusian / Ukrainian ў is a distinct letter.
        assert normalize_text("Беларусь — мова ў сэрцы") == "Беларусь - мова ў сэрцы"

    def test_dashes_still_normalised_inside_cyrillic(self):
        assert normalize_text("Война — и мир") == "Война - и мир"


# ── Greek: polytonic accents preserved, but dashes still normalise ─────────


class TestGreekPreserved:
    def test_kazantzakis_preserved(self):
        # Νίκος Καζαντζάκης — Greek author. Accents are integral to
        # the modern monotonic system and the polytonic of classical
        # texts; stripping them is a data-loss bug.
        assert normalize_text("Νίκος Καζαντζάκης") == "Νίκος Καζαντζάκης"

    def test_polytonic_accents_preserved(self):
        # ψυχή with the acute accent on the eta.
        assert normalize_text("ψυχή") == "ψυχή"


# ── Hebrew and Arabic vowel marks preserved ────────────────────────────────


class TestHebrewArabicPreserved:
    def test_hebrew_with_niqqud_preserved(self):
        # שָׁלוֹם — 'peace' with niqqud (vowel points). These are usually
        # absent from text but when present they disambiguate readings.
        text = "שָׁלוֹם"
        assert normalize_text(text) == text

    def test_hebrew_plain_preserved(self):
        assert normalize_text("עמוס עוז") == "עמוס עוז"  # Amos Oz

    def test_arabic_with_vowel_marks_preserved(self):
        # بَيْت — 'house' with vowel marks (harakat).
        text = "بَيْت"
        assert normalize_text(text) == text

    def test_arabic_plain_preserved(self):
        # نجيب محفوظ — Naguib Mahfouz.
        assert normalize_text("نجيب محفوظ") == "نجيب محفوظ"


# ── CJK and emoji pass through ─────────────────────────────────────────────


class TestCjkAndEmoji:
    def test_japanese_preserved(self):
        # 村上春樹 — Haruki Murakami.
        assert normalize_text("村上春樹") == "村上春樹"

    def test_chinese_preserved(self):
        assert normalize_text("红楼梦") == "红楼梦"  # Dream of the Red Chamber

    def test_korean_preserved(self):
        # 한강 — Han Kang, Nobel laureate.
        assert normalize_text("한강") == "한강"

    def test_mixed_cjk_and_latin(self):
        # Common in publisher metadata: original-language title with
        # Latin transliteration. Dash normalises, CJK intact.
        assert (
            normalize_text("村上春樹 — The Wind-Up Bird Chronicle")
            == "村上春樹 - The Wind-Up Bird Chronicle"
        )

    def test_emoji_preserved(self):
        # We don't expect emoji in titles, but if one slips in we should
        # not silently mangle it.
        assert normalize_text("Title with 😀 emoji") == "Title with 😀 emoji"


# ── Latin Americanization still works (regression guard) ───────────────────


class TestLatinStillStripped:
    """The original intent of normalize_text — Latin → ASCII — must
    not regress as a result of the script-awareness fix."""

    @pytest.mark.parametrize("inp,want", [
        ("café", "cafe"),
        ("Müller", "Muller"),
        ("naïve", "naive"),
        ("Ångström", "Angstrom"),
        ("Straße", "Strasse"),
        ("Encyclopædia", "Encyclopaedia"),
        ("cœur", "coeur"),
        ("Łódź", "Lodz"),
        ("Đorđe", "Dorde"),
        ("Þór", "Thor"),
    ])
    def test_latin_diacritics_still_strip(self, inp, want):
        assert remove_diacritics(inp) == want

    def test_full_pipeline_dashes_and_latin(self):
        assert normalize_text("Café — Müller") == "Cafe - Muller"

    def test_mixed_latin_and_cyrillic(self):
        # Latin half Americanizes; Cyrillic half preserved.
        assert (
            normalize_text("Café Достоевский")
            == "Cafe Достоевский"
        )


# ── Identifier sanitization ────────────────────────────────────────────────


class TestSanitizeIdentifier:
    def test_clean_pair_returned_unchanged(self):
        assert _sanitize_identifier("isbn", "9780394720241") == ("isbn", "9780394720241")

    def test_key_lowercased(self):
        assert _sanitize_identifier("ISBN", "9780394720241") == ("isbn", "9780394720241")

    def test_whitespace_stripped(self):
        assert _sanitize_identifier("  isbn  ", "  9780394720241  ") == (
            "isbn", "9780394720241",
        )

    @pytest.mark.parametrize("empty_key", ["", " ", "\t", "\n"])
    def test_empty_key_rejected(self, empty_key):
        assert _sanitize_identifier(empty_key, "9780394720241") is None

    @pytest.mark.parametrize("empty_value", ["", " ", "\t"])
    def test_empty_value_rejected(self, empty_value):
        assert _sanitize_identifier("isbn", empty_value) is None

    def test_reserved_calibre_key_rejected(self):
        assert _sanitize_identifier("calibre", "anything") is None
        assert _sanitize_identifier("CALIBRE", "anything") is None  # case-insensitive

    def test_comma_in_value_rejected(self):
        """Pre-v1.3 behaviour: comma was already filtered (it would
        corrupt the identifiers field's outer separator)."""
        assert _sanitize_identifier("isbn", "9780394,720241") is None

    def test_colon_in_value_rejected(self):
        """Item 15 regression: pre-v1.3 the docstring claimed colon was
        filtered but the code didn't actually check. Now it does."""
        assert _sanitize_identifier("amazon", "B07X:5RH") is None

    def test_comma_in_key_rejected(self):
        """Comma in the key would also corrupt the field. Pre-v1.3 keys
        weren't sanitised at all."""
        assert _sanitize_identifier("is,bn", "9780394720241") is None

    def test_colon_in_key_rejected(self):
        assert _sanitize_identifier("is:bn", "9780394720241") is None

    def test_whitespace_inside_key_rejected(self):
        """Identifier types are conventionally lowercase alphanumeric.
        A space in the key is a sign of bad input."""
        assert _sanitize_identifier("good reads", "12345") is None

    @pytest.mark.parametrize("bad_char", ["\n", "\r", "\t", "\x00", "\x1b"])
    def test_control_char_in_value_rejected(self, bad_char):
        assert _sanitize_identifier("isbn", f"9780394{bad_char}720241") is None

    def test_zero_width_joiner_in_value_rejected(self):
        """Invisible Cf-category characters silently break exact-match
        searches downstream; reject them."""
        # ‍ = zero-width joiner. Common copy-paste accident.
        assert _sanitize_identifier("isbn", "9780394‍720241") is None

    def test_bidi_mark_in_value_rejected(self):
        # ‏ = RTL mark. Same reason.
        assert _sanitize_identifier("isbn", "9780394‏720241") is None

    def test_unicode_in_value_preserved(self):
        """Unicode letters (Lo / Lu / Ll) are fine in values — some
        identifiers (LCCN, foreign catalog IDs) legitimately use them."""
        result = _sanitize_identifier("local", "Достоевский-1881")
        assert result == ("local", "Достоевский-1881")

    def test_non_string_inputs_rejected(self):
        assert _sanitize_identifier(None, "x") is None       # type: ignore[arg-type]
        assert _sanitize_identifier("isbn", None) is None    # type: ignore[arg-type]
        assert _sanitize_identifier(42, "x") is None         # type: ignore[arg-type]


# ── apply_identifiers integration ─────────────────────────────────────────


class TestApplyIdentifiersUsesSanitizer:
    """Smoke-test that apply_identifiers drops the same set of bad
    entries that _sanitize_identifier rejects in isolation. We do this
    by monkeypatching subprocess.run and inspecting the command line
    the method would have invoked."""

    def test_apply_identifiers_filters_colon_value(self, tmp_path, monkeypatch):
        from calibre_toolkit.db import CalibreDB
        from unittest.mock import MagicMock

        # CalibreDB checks metadata.db exists at construction time.
        (tmp_path / "metadata.db").touch()
        db = CalibreDB(calibredb_path="calibredb", library_path=str(tmp_path))
        captured: list[list[str]] = []

        def fake_run(cmd, *a, **kw):
            captured.append(cmd)
            return MagicMock(returncode=0, stderr="")

        monkeypatch.setattr("calibre_toolkit.db.subprocess.run", fake_run)

        db.apply_identifiers(1, {
            "isbn":     "9780394720241",
            "amazon":   "B07X:5RH",      # colon — rejected
            "good,bad": "123",            # comma in key — rejected
            "calibre":  "ignored",        # reserved key — rejected
            "":         "ignored",        # empty key — rejected
            "lccn":     "2024012345",
        })

        assert len(captured) == 1
        # The --field argument carries the identifiers payload.
        field_arg_idx = captured[0].index("--field") + 1
        field_value = captured[0][field_arg_idx]
        # Both good entries are present; bad entries are gone.
        assert "isbn:9780394720241" in field_value
        assert "lccn:2024012345" in field_value
        assert "amazon" not in field_value
        assert "good" not in field_value
        assert "calibre" not in field_value
