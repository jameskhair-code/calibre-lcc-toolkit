"""Tests for ai._extract_json_array / ai._extract_json_object.

The extractors are the only line of defence against the model adding
markdown fences, prose preambles, or trailing commentary. They must succeed
on every reasonable variant and fail loudly on truly broken input.
"""

import pytest

from calibre_toolkit.ai import _extract_json_array, _extract_json_object


class TestExtractJsonArray:
    def test_plain_array(self):
        assert _extract_json_array('[{"id": 1}]') == [{"id": 1}]

    def test_with_markdown_fence(self):
        raw = '```json\n[{"id": 1, "title": "X"}]\n```'
        assert _extract_json_array(raw) == [{"id": 1, "title": "X"}]

    def test_with_prose_preamble(self):
        raw = 'Here is the result you asked for:\n[{"id": 7}]'
        assert _extract_json_array(raw) == [{"id": 7}]

    def test_with_trailing_commentary(self):
        raw = '[{"id": 1}]\n\nLet me know if you need anything else.'
        assert _extract_json_array(raw) == [{"id": 1}]

    def test_multiline_pretty_printed(self):
        raw = """
        Here you go:
        [
          {"id": 1, "tags": ["a", "b"]},
          {"id": 2, "tags": ["c"]}
        ]
        """
        result = _extract_json_array(raw)
        assert len(result) == 2
        assert result[0]["tags"] == ["a", "b"]

    def test_empty_array(self):
        assert _extract_json_array("[]") == []

    def test_no_brackets_raises(self):
        with pytest.raises(RuntimeError, match="no JSON array"):
            _extract_json_array("just some prose, no JSON anywhere")

    def test_invalid_json_raises(self):
        # Brackets present but contents are malformed
        with pytest.raises(RuntimeError, match="invalid JSON"):
            _extract_json_array("[{not valid json}]")

    def test_swapped_brackets_raises(self):
        with pytest.raises(RuntimeError, match="no JSON array"):
            _extract_json_array("] [")


class TestExtractJsonObject:
    def test_plain_object(self):
        assert _extract_json_object('{"a": 1}') == {"a": 1}

    def test_with_markdown_fence(self):
        raw = '```json\n{"assessment": "complete", "confidence": "high"}\n```'
        assert _extract_json_object(raw) == {
            "assessment": "complete",
            "confidence": "high",
        }

    def test_with_prose_preamble(self):
        raw = 'My assessment is:\n{"assessment": "needs_additions"}'
        assert _extract_json_object(raw) == {"assessment": "needs_additions"}

    def test_no_braces_raises(self):
        with pytest.raises(RuntimeError, match="no JSON object"):
            _extract_json_object("nothing useful here")

    def test_invalid_object_raises(self):
        with pytest.raises(RuntimeError, match="invalid JSON"):
            _extract_json_object("{ broken }")
