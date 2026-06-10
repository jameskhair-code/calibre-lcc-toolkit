"""
AI client (Anthropic-only).

Books are sent in batches and processed concurrently to minimise wall time.
The system prompt for each command is cached via Anthropic prompt caching so
that successive batches in the same run pay near-zero for the (large) rules
file portion of the prompt.

Package layout (v1.9 item 3 — split from the former single-file ai.py):

- `_client.py`  — AIClient (telemetry, retries, batching, the suggest_*
  surface), BatchFailure, the shared JSON extractors.
- `_prompts.py` — rules/prompt-fragment loading shared by the step modules.
- `authors.py` / `lcc.py` / `tags.py` / `comments.py` — per-step suggestion
  dataclasses, prompt assembly, and response parse/validate/transform.
  (No identifiers module: that step uses fetcher.py, not the AI.)

Every name the former ai.py exposed at module level is re-exported here, so
`from calibre_toolkit.ai import <anything>` keeps resolving unchanged.
"""

from __future__ import annotations

from ._prompts import (
    _PROMPTS_DIR,
    _RULES_DIR,
    _load_prompt,
    _load_rules,
)
from .authors import (
    CleanupSuggestion,
    _author_compare_key,
    _build_system_prompt,
    _build_user_message,
    _parse_response,
    _transform_cleanup_items,
)
from .lcc import (
    LccSuggestion,
    SourceAuthority,
    _ATTRIBUTION_PREFIX,
    _SOURCE_AUTHORITY_VALUES,
    _build_lcc_summary_system_prompt,
    _build_lcc_summary_user_message,
    _build_lcc_system_prompt,
    _build_lcc_user_message,
    _normalise_lcc_source_authority,
    _parse_lcc_response,
    _transform_lcc_items,
)
from .tags import (
    TagOperation,
    TagsReviewSuggestion,
    TagsSuggestion,
    _FORM_TAGS,
    _build_tag_cleanup_system_prompt,
    _build_tag_cleanup_user_message,
    _build_tags_review_system_prompt,
    _build_tags_review_user_message,
    _build_tags_system_prompt,
    _build_tags_user_message,
    _parse_tag_cleanup_response,
    _parse_tags_response,
    _parse_tags_review_response,
    _transform_tag_cleanup_ops,
    _transform_tags_items,
    _transform_tags_review_item,
    _validate_proposed_tags,
)
from .comments import (
    CommentsSuggestion,
    _ALLOWED_HTML_TAGS,
    _COMMENTS_SECTION_KEYS,
    _CommentsHTMLValidator,
    _VOID_HTML_TAGS,
    _build_comments_system_prompt,
    _build_comments_user_message,
    _coerce_score,
    _format_comments_html,
    _parse_comments_response,
    _transform_comments_items,
    validate_comments_html,
)
from ._client import (
    AIClient,
    BatchFailure,
    _extract_json_array,
    _extract_json_object,
)
