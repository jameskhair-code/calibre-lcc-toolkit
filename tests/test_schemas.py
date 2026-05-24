"""Pydantic schema validators + AIClient._call_with_validation retry loop.

The validators are pure functions over strings; the retry-loop tests stub
`AIClient._call` so we never touch the Anthropic SDK.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from calibre_toolkit.ai import AIClient
from calibre_toolkit.schemas import (
    CleanupItem,
    CommentsItem,
    LccItem,
    SchemaViolation,
    TagCleanupOp,
    TagsItem,
    TagsReviewResponse,
    build_correction_prompt,
    validate_cleanup,
    validate_comments,
    validate_lcc,
    validate_tag_cleanup,
    validate_tags,
    validate_tags_review,
)


# ── validate_cleanup ────────────────────────────────────────────────────────


class TestValidateCleanup:
    def test_happy_path(self):
        raw = json.dumps([
            {"id": 1, "title": "Foo", "authors": ["A"], "confidence": "high", "notes": ""},
            {"id": 2, "title": "Bar", "authors": ["B"], "confidence": "medium", "notes": ""},
        ])
        items = validate_cleanup(raw)
        assert len(items) == 2
        assert isinstance(items[0], CleanupItem)
        assert items[0].title == "Foo"

    def test_missing_id_rejected(self):
        raw = json.dumps([{"title": "Foo", "confidence": "high"}])
        with pytest.raises(SchemaViolation):
            validate_cleanup(raw)

    def test_invalid_confidence_rejected(self):
        raw = json.dumps([{"id": 1, "title": "T", "confidence": "absolute"}])
        with pytest.raises(SchemaViolation):
            validate_cleanup(raw)

    def test_extracts_array_from_fenced_response(self):
        raw = "```json\n" + json.dumps([{"id": 1, "title": "T", "confidence": "high"}]) + "\n```"
        items = validate_cleanup(raw)
        assert items[0].id == 1

    def test_no_array_in_response_rejected(self):
        with pytest.raises(SchemaViolation):
            validate_cleanup("just prose, no JSON here.")

    def test_default_authors_empty(self):
        raw = json.dumps([{"id": 1, "title": "T", "confidence": "high"}])
        items = validate_cleanup(raw)
        assert items[0].authors == []


# ── validate_lcc ────────────────────────────────────────────────────────────


class TestValidateLcc:
    def test_happy_path(self):
        raw = json.dumps([{
            "id": 1, "lcc": "PR6059", "lcc_primary_class": "P",
            "lcc_secondary_class": "PR", "lcc_summary": "X.",
            "confidence": "high", "source": "LC catalog", "notes": "",
        }])
        items = validate_lcc(raw)
        assert items[0].lcc == "PR6059"

    def test_invalid_confidence_rejected(self):
        raw = json.dumps([{"id": 1, "lcc": "PR", "confidence": "totally sure"}])
        with pytest.raises(SchemaViolation):
            validate_lcc(raw)


# ── validate_comments ──────────────────────────────────────────────────────


class TestValidateComments:
    def test_happy_path(self):
        raw = json.dumps([{
            "id": 1, "book_type": "fiction", "the_story": "summary",
            "must_read_score": 7, "must_read_rationale": "good",
            "confidence": "high", "notes": "",
        }])
        items = validate_comments(raw)
        assert isinstance(items[0], CommentsItem)
        assert items[0].book_type == "fiction"
        assert items[0].must_read_score == 7

    def test_book_type_normalised(self):
        raw = json.dumps([{
            "id": 1, "book_type": " FICTION ", "confidence": "high",
        }])
        items = validate_comments(raw)
        assert items[0].book_type == "fiction"

    def test_invalid_book_type_rejected(self):
        raw = json.dumps([{"id": 1, "book_type": "memoir", "confidence": "high"}])
        with pytest.raises(SchemaViolation):
            validate_comments(raw)

    def test_string_score_passes_through(self):
        """The Pydantic model accepts int|str|None; coercion happens later in ai._coerce_score."""
        raw = json.dumps([{
            "id": 1, "book_type": "fiction", "must_read_score": "7",
            "confidence": "high",
        }])
        items = validate_comments(raw)
        assert items[0].must_read_score == "7"


# ── validate_tags ──────────────────────────────────────────────────────────


class TestValidateTags:
    def test_happy_path(self):
        raw = json.dumps([{"id": 1, "tags": ["Novel", "Mystery"], "confidence": "high", "notes": ""}])
        items = validate_tags(raw)
        assert items[0].tags == ["Novel", "Mystery"]

    def test_top_level_not_array_rejected(self):
        # Validate that an object where an array is expected raises.
        raw = json.dumps({"id": 1, "tags": []})
        with pytest.raises(SchemaViolation):
            validate_tags(raw)


# ── validate_tags_review ───────────────────────────────────────────────────


class TestValidateTagsReview:
    def test_happy_path(self):
        raw = json.dumps({
            "assessment": "needs_additions",
            "proposed_tags": ["Novel", "Mystery"],
            "confidence": "high",
            "notes": "Adding subject tag.",
        })
        obj = validate_tags_review(raw)
        assert isinstance(obj, TagsReviewResponse)
        assert obj.assessment == "needs_additions"

    def test_invalid_assessment_rejected(self):
        raw = json.dumps({"assessment": "great", "proposed_tags": [], "confidence": "high"})
        with pytest.raises(SchemaViolation):
            validate_tags_review(raw)


# ── validate_tag_cleanup ───────────────────────────────────────────────────


class TestValidateTagCleanup:
    def test_happy_path(self):
        raw = json.dumps([
            {"source_tags": ["sci-fi"], "target_tags": ["Science Fiction"], "reason": "canon"},
        ])
        ops = validate_tag_cleanup(raw)
        assert isinstance(ops[0], TagCleanupOp)
        assert ops[0].source_tags == ["sci-fi"]


# ── build_correction_prompt ────────────────────────────────────────────────


class TestCorrectionPrompt:
    def test_includes_original_message_and_error(self):
        try:
            validate_tags("not JSON")
        except SchemaViolation as e:
            prompt = build_correction_prompt("ORIGINAL_PAYLOAD_TOKEN", e)
        assert "ORIGINAL_PAYLOAD_TOKEN" in prompt
        assert "schema validation" in prompt.lower()


# ── _call_with_validation retry flow ──────────────────────────────────────


def _make_client() -> AIClient:
    # Pass a non-empty api_key so the constructor accepts it; we never call out.
    return AIClient(api_key="test-key", model="claude-test")


class TestCallWithValidationRetry:
    def test_first_call_succeeds_no_retry(self):
        client = _make_client()
        good = json.dumps([{"id": 1, "title": "T", "confidence": "high", "notes": ""}])

        with patch.object(AIClient, "_call", return_value=good) as mock_call:
            items = client._call_with_validation(
                "user", "system", validate_cleanup,
            )

        assert len(items) == 1
        assert mock_call.call_count == 1

    def test_first_call_fails_retry_succeeds(self):
        client = _make_client()
        bad = "not valid JSON"
        good = json.dumps([{"id": 1, "title": "T", "confidence": "high", "notes": ""}])

        with patch.object(AIClient, "_call", side_effect=[bad, good]) as mock_call:
            items = client._call_with_validation(
                "user", "system", validate_cleanup,
            )

        assert len(items) == 1
        assert mock_call.call_count == 2

    def test_both_calls_fail_raises(self):
        client = _make_client()
        with patch.object(AIClient, "_call", side_effect=["bad1", "bad2"]) as mock_call:
            with pytest.raises(SchemaViolation):
                client._call_with_validation(
                    "user", "system", validate_cleanup,
                )
        assert mock_call.call_count == 2

    def test_correction_prompt_quotes_first_error(self):
        client = _make_client()
        good = json.dumps([{"id": 1, "title": "T", "confidence": "high"}])
        captured_msgs: list[str] = []

        def fake_call(self_, user, system, max_tokens=8192):
            captured_msgs.append(user)
            if len(captured_msgs) == 1:
                return "not JSON"
            return good

        with patch.object(AIClient, "_call", side_effect=lambda *a, **kw: fake_call(client, *a, **kw)):
            client._call_with_validation("ORIG_USER_MSG", "system", validate_cleanup)

        # First user message is the original; second includes correction framing and original.
        assert captured_msgs[0] == "ORIG_USER_MSG"
        assert "ORIG_USER_MSG" in captured_msgs[1]
        assert "schema validation" in captured_msgs[1].lower()
