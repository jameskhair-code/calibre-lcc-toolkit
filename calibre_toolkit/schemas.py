"""
Pydantic response schemas for AI calls.

Before v1.2 item 7, `_extract_json_*` in `ai.py` parsed AI responses but
did not validate shape. Most violations propagated silently — e.g. the
Form-tag check in `_validate_proposed_tags` downgraded confidence after
the fact rather than catching the error at generation time, and a free-
text `confidence` field could land as a string outside the documented
`high|medium|low` enum.

Each model below mirrors the JSON object documented in the corresponding
OUTPUT FORMAT block of `ai.py`. `validate_*` helpers parse the raw model
text and raise `SchemaViolation` on any shape error, so the
`AIClient._call_with_validation` retry loop has a single exception type
to key on.

These schemas validate shape only. Domain rules (FORM-01, must-read
score coercion, etc.) continue to live in the existing transform
functions in `ai.py`.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


Confidence = Literal["high", "medium", "low"]


class SchemaViolation(Exception):
    """Raised when a model response fails Pydantic validation.

    The message includes Pydantic's full error list so the retry prompt
    can quote it back to the model for correction.
    """

    def __init__(self, message: str, *, raw: str | None = None):
        super().__init__(message)
        self.raw = raw


# ── Per-step item schemas ───────────────────────────────────────────────────


class CleanupItem(BaseModel):
    """clean-titles response row."""
    model_config = ConfigDict(extra="ignore")
    id: int
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    confidence: Confidence = "medium"
    notes: str = ""


class LccItem(BaseModel):
    """lcc-enrich response row."""
    model_config = ConfigDict(extra="ignore")
    id: int
    lcc: str = ""
    lcc_primary_class: str = ""
    lcc_secondary_class: str = ""
    lcc_summary: str = ""
    confidence: Confidence = "low"
    source: str = ""
    # Structural provenance — enforced by _normalise_lcc_source_authority in
    # ai.py, which downgrades unsupported lc_catalog/worldcat_consensus claims.
    # Accept any string here; the normaliser handles bad values rather than
    # raising a SchemaViolation (we don't want one bad enum to fail the row).
    source_authority: str = ""
    notes: str = ""


class LccSummaryItem(BaseModel):
    """v1.7 item 5 — summary-only response row.

    Used when the OL catalog has already provided lcc/primary/secondary
    and the AI is called solely for the prose summary. An empty
    lcc_summary signals an identity mismatch — the caller keeps the
    catalog-template summary rather than write prose grounded in the
    wrong work.
    """
    model_config = ConfigDict(extra="ignore")
    id: int
    lcc_summary: str = ""


class CommentsItem(BaseModel):
    """comments-enrich response row."""
    model_config = ConfigDict(extra="ignore")
    id: int
    book_type: Literal["fiction", "nonfiction", ""] = ""
    the_book: str = ""
    the_argument: str = ""
    the_story: str = ""
    what_its_really_about: str = ""
    something_you_might_not_know: str = ""
    why_read_it: str = ""
    must_read_score: int | str | None = None
    must_read_rationale: str = ""
    confidence: Confidence = "low"
    notes: str = ""

    @field_validator("book_type", mode="before")
    @classmethod
    def _normalise_book_type(cls, v):
        if v is None:
            return ""
        return str(v).strip().lower()


class TagsItem(BaseModel):
    """tags-enrich response row."""
    model_config = ConfigDict(extra="ignore")
    id: int
    tags: list[str] = Field(default_factory=list)
    confidence: Confidence = "low"
    notes: str = ""


class TagsReviewResponse(BaseModel):
    """tags-review single-book response object."""
    model_config = ConfigDict(extra="ignore")
    assessment: Literal["complete", "needs_additions", "needs_corrections"] = "complete"
    proposed_tags: list[str] = Field(default_factory=list)
    confidence: Confidence = "medium"
    notes: str = ""


class TagCleanupOp(BaseModel):
    """tags-cleanup single operation."""
    model_config = ConfigDict(extra="ignore")
    source_tags: list[str] = Field(default_factory=list)
    target_tags: list[str] = Field(default_factory=list)
    reason: str = ""


# ── Extractors ──────────────────────────────────────────────────────────────


def _slice_outer(raw: str, opener: str, closer: str) -> str:
    """Return the substring from the first `opener` to the last `closer`."""
    start = raw.find(opener)
    end = raw.rfind(closer)
    if start == -1 or end == -1 or end <= start:
        raise SchemaViolation(
            f"AI returned no JSON {opener}{closer}.\n\nRaw response:\n{raw[:500]}",
            raw=raw,
        )
    return raw[start : end + 1]


def _load_json(raw: str, expected: type) -> object:
    """Extract the outermost JSON value of the expected container type.

    Markdown fences and stray prose around the JSON are tolerated, but a
    top-level value of the wrong container type (e.g. an object when an
    array was expected) is rejected — silently slicing out an inner `[]`
    or `{}` would mask a real shape error.
    """
    # Detect the real top-level container by peeking past leading whitespace
    # and any markdown ```json fence.
    stripped = raw.lstrip()
    if stripped.startswith("```"):
        # Drop the opening fence (and any "json" language tag) and the
        # closing fence (if any) so we look at the actual payload.
        nl = stripped.find("\n")
        if nl != -1:
            stripped = stripped[nl + 1:]
        end_fence = stripped.rfind("```")
        if end_fence != -1:
            stripped = stripped[:end_fence]
        stripped = stripped.lstrip()
    first = stripped[:1]
    if expected is list and first == "{":
        raise SchemaViolation("expected a JSON array, got an object", raw=raw)
    if expected is dict and first == "[":
        raise SchemaViolation("expected a JSON object, got an array", raw=raw)

    if expected is list:
        text = _slice_outer(raw, "[", "]")
    elif expected is dict:
        text = _slice_outer(raw, "{", "}")
    else:
        raise TypeError(f"unsupported expected container {expected!r}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SchemaViolation(f"AI returned invalid JSON: {e}", raw=raw) from e


def _validate_list(raw: str, model: type[BaseModel]) -> list[BaseModel]:
    data = _load_json(raw, list)
    if not isinstance(data, list):
        raise SchemaViolation(
            f"expected a JSON array, got {type(data).__name__}", raw=raw,
        )
    try:
        return [model.model_validate(item) for item in data]
    except ValidationError as e:
        raise SchemaViolation(
            f"response failed {model.__name__} validation:\n{e}", raw=raw,
        ) from e


def _validate_object(raw: str, model: type[BaseModel]) -> BaseModel:
    data = _load_json(raw, dict)
    if not isinstance(data, dict):
        raise SchemaViolation(
            f"expected a JSON object, got {type(data).__name__}", raw=raw,
        )
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise SchemaViolation(
            f"response failed {model.__name__} validation:\n{e}", raw=raw,
        ) from e


def validate_cleanup(raw: str) -> list[CleanupItem]:
    return _validate_list(raw, CleanupItem)


def validate_lcc(raw: str) -> list[LccItem]:
    return _validate_list(raw, LccItem)


def validate_lcc_summary(raw: str) -> list[LccSummaryItem]:
    return _validate_list(raw, LccSummaryItem)


def validate_comments(raw: str) -> list[CommentsItem]:
    return _validate_list(raw, CommentsItem)


def validate_tags(raw: str) -> list[TagsItem]:
    return _validate_list(raw, TagsItem)


def validate_tags_review(raw: str) -> TagsReviewResponse:
    return _validate_object(raw, TagsReviewResponse)


def validate_tag_cleanup(raw: str) -> list[TagCleanupOp]:
    return _validate_list(raw, TagCleanupOp)


# ── Correction prompt ───────────────────────────────────────────────────────


def build_correction_prompt(original_user_msg: str, error: SchemaViolation) -> str:
    """Compose a follow-up user message asking the model to fix the schema
    violation. Quotes the Pydantic error verbatim so the model knows exactly
    what to correct.
    """
    return (
        "Your previous response failed schema validation. Please re-issue it "
        "with the documented JSON shape and no extra commentary.\n\n"
        f"Validation error:\n{error}\n\n"
        "Original request follows — respond again, in the same order, with "
        "exactly the documented keys and types.\n\n"
        f"{original_user_msg}"
    )
