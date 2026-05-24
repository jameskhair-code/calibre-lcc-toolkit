"""Tests for item 10 — externalized prompts + unified confidence taxonomy.

The preambles and output-format blocks that used to live in ai.py as inline
string literals now load from rules/prompts/*.md. These tests verify that
the externalized fragments are present, that the system prompts compose
the expected parts, and that no inline literal silently drifts back into
ai.py.
"""

from __future__ import annotations
from pathlib import Path

import calibre_toolkit.ai as ai

_RULES_DIR = Path(ai.__file__).parent.parent / "rules"
_PROMPTS_DIR = _RULES_DIR / "prompts"


def test_confidence_rules_file_exists():
    path = _RULES_DIR / "confidence.md"
    assert path.exists(), "rules/confidence.md must exist as the canonical tier definition"
    text = path.read_text(encoding="utf-8")
    for marker in ("CONF-T-HIGH", "CONF-T-MEDIUM", "CONF-T-LOW"):
        assert marker in text, f"confidence.md must define {marker}"


def test_prompt_fragments_all_present():
    expected = [
        "author_title_preamble.md",
        "author_title_output_format.md",
        "lcc_preamble.md",
        "lcc_output_format.md",
        "comments_preamble.md",
        "comments_output_format.md",
        "tags_preamble.md",
        "tags_output_format.md",
        "tag_cleanup_preamble.md",
        "tags_review_system.md",
    ]
    for name in expected:
        path = _PROMPTS_DIR / name
        assert path.exists(), f"prompt fragment missing: {path}"
        assert path.read_text(encoding="utf-8").strip(), f"prompt fragment empty: {path}"


def test_load_prompt_helper_round_trips():
    text = ai._load_prompt("lcc_preamble.md")
    assert "Library of Congress Classification" in text


def test_load_prompt_missing_file_raises():
    import pytest
    with pytest.raises(FileNotFoundError):
        ai._load_prompt("does_not_exist.md")


def test_author_title_system_prompt_composes_preamble_rules_format():
    prompt = ai._build_system_prompt("author_title.md")
    assert "metadata librarian specialising in literary fiction" in prompt
    assert "OUTPUT FORMAT" in prompt
    assert '"id": <integer>' in prompt
    # The rules content sits between preamble and output format.
    rules_text = (_RULES_DIR / "author_title.md").read_text(encoding="utf-8")
    # Sample a distinctive substring from the rules file.
    sample = rules_text.strip().splitlines()[0]
    assert sample in prompt


def test_lcc_system_prompt_includes_source_authority_block_and_rules():
    prompt = ai._build_lcc_system_prompt()
    assert "propagating Library of Congress Classification" in prompt
    assert "source_authority" in prompt
    assert "ai_inference" in prompt
    # Rules content present.
    assert "SCOPE-01" in prompt
    # Confidence rules reference confidence.md.
    assert "rules/confidence.md" in prompt


def test_comments_system_prompt_includes_reader_profile_and_format():
    prompt = ai._build_comments_system_prompt()
    assert "READER PROFILE" in prompt
    assert "STRUCTURAL RULES" in prompt
    assert "must_read_score" in prompt
    assert "generating book descriptions" in prompt


def test_tags_system_prompt_includes_rules_and_format():
    prompt = ai._build_tags_system_prompt()
    assert "subject tags" in prompt
    assert '"tags": ["Tag One"' in prompt
    # Tag rules content.
    assert "SCOPE-01" in prompt


def test_tag_cleanup_system_prompt_includes_rules():
    prompt = ai._build_tag_cleanup_system_prompt()
    assert "normalizing the tag vocabulary" in prompt
    # tags_cleanup.md content follows.
    cleanup_rules = (_RULES_DIR / "tags_cleanup.md").read_text(encoding="utf-8")
    sample = cleanup_rules.strip().splitlines()[0]
    assert sample in prompt


def test_tags_review_system_prompt_is_externalized():
    prompt = ai._build_tags_review_system_prompt()
    assert "assessing subject tags" in prompt
    assert "OUTPUT FORMAT" in prompt
    assert '"assessment"' in prompt
    assert "rules/confidence.md" in prompt


def test_ai_module_has_no_remaining_inline_preamble_constants():
    """Guard rail: if a future change reintroduces an inline preamble, this
    test fails so the reviewer can move it back to rules/prompts/."""
    forbidden = [
        "_PROMPT_PREAMBLE",
        "_PROMPT_OUTPUT_FORMAT",
        "_LCC_PROMPT_PREAMBLE",
        "_LCC_PROMPT_OUTPUT_FORMAT",
        "_COMMENTS_PROMPT_PREAMBLE",
        "_COMMENTS_OUTPUT_FORMAT",
        "_TAGS_PROMPT_PREAMBLE",
        "_TAGS_OUTPUT_FORMAT",
        "_TAGS_REVIEW_SYSTEM_PROMPT",
    ]
    for name in forbidden:
        assert not hasattr(ai, name), (
            f"ai.{name} reintroduced — keep prompt prose in rules/prompts/"
        )


def test_step_rules_reference_shared_confidence_file():
    """Each step's CONF section should point readers at rules/confidence.md."""
    for rules_file in ("lcc.md", "comments.md", "tags.md"):
        text = (_RULES_DIR / rules_file).read_text(encoding="utf-8")
        assert "rules/confidence.md" in text, (
            f"{rules_file} should reference rules/confidence.md from its CONF section"
        )
