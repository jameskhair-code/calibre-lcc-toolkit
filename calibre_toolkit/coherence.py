"""Cross-step coherence checks (roadmap item 16).

Steps 04 (comments) and 05 (tags) run independently. Each can produce
output that contradicts the other — most visibly, a comment that
discusses the Cold War while the tag set has no period tag, or a tag
set with "World War II" while the prose never touches the period.

These checks are deliberately small and curated. False positives kill
trust faster than false negatives, so the keyword map is restricted
to a handful of high-signal historical periods where the
prose-vs-tags coupling is unambiguous. Subject coherence (e.g.
"this book is about jazz but no jazz tag") is left out — too many
ways for a comment to discuss a thing without it deserving a tag.

The checkers return human-readable warning strings. Empty list means
nothing flagged. Callers (modules/comments.py, modules/tags.py)
surface the warnings in their review tables, the same way
html_warnings are surfaced today.
"""

from __future__ import annotations

import html
import re


# Period name → set of acceptable tag forms. Tag forms are matched
# case-insensitively against the AI's proposed tags. Multiple
# acceptable forms cover legitimate spelling variants (Roman numerals
# vs. arabic, "WWII" vs. "World War II", etc.). Keep this list short.
_PERIOD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Cold War":        ("Cold War",),
    "World War II":    ("World War II", "World War 2", "WWII", "Second World War"),
    "World War I":     ("World War I", "World War 1", "WWI", "First World War", "Great War"),
    "Vietnam War":     ("Vietnam War",),
    "Korean War":      ("Korean War",),
    "Civil War":       ("Civil War", "American Civil War"),
    "The Troubles":    ("The Troubles", "Northern Ireland Conflict"),
    "Victorian Era":   ("Victorian Era", "Victorian"),
    "Reconstruction":  ("Reconstruction",),
    "French Revolution": ("French Revolution",),
    "Russian Revolution": ("Russian Revolution",),
}


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities from a snippet of comment HTML.

    Used so the keyword matcher works against the raw prose the
    reader would actually see, not against `<h3>The Story</h3>` etc.
    """
    no_tags = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(no_tags)


def _prose_mentions(prose: str, variants: tuple[str, ...]) -> bool:
    """True when any spelling variant appears in the prose as a whole word.

    Word-boundary matching avoids "war" matching inside "warden". The
    variants include multi-word phrases, so the regex respects the
    full phrase, not just its tokens.
    """
    text = prose.lower()
    for v in variants:
        pattern = r"\b" + re.escape(v.lower()) + r"\b"
        if re.search(pattern, text):
            return True
    return False


def _tags_include(tags: list[str], variants: tuple[str, ...]) -> bool:
    tag_lower = {t.strip().lower() for t in tags}
    return any(v.lower() in tag_lower for v in variants)


def check_comments_coherence(
    comments_html_or_prose: str,
    current_tags: list[str],
) -> list[str]:
    """Flag periods named in the AI prose that have no matching tag.

    Called from modules/comments.py after AI suggestions return. The
    `current_tags` here are the *current* tags on the book — the
    comments step does not propose new tags, so it can only flag
    "prose names a period the book is not currently tagged for."
    """
    if not comments_html_or_prose:
        return []
    prose = _strip_html(comments_html_or_prose)
    warnings: list[str] = []
    for canonical, variants in _PERIOD_KEYWORDS.items():
        if _prose_mentions(prose, variants) and not _tags_include(current_tags, variants):
            warnings.append(
                f"Prose mentions “{canonical}” but no matching period tag is set."
            )
    return warnings


def check_tags_coherence(
    proposed_tags: list[str],
    comments_excerpt: str,
) -> list[str]:
    """Flag period tags the AI proposed that are not supported by the book's prose.

    Called from modules/tags.py after AI suggestions return. The
    excerpt is the existing comments field — stripped HTML, trimmed
    to a few hundred chars. When the AI adds e.g. "Cold War" but the
    comments excerpt never mentions it, that may be a real signal
    miss or it may be an over-eager tag — the reviewer decides.
    """
    if not proposed_tags or not comments_excerpt:
        return []
    prose = _strip_html(comments_excerpt)
    warnings: list[str] = []
    for canonical, variants in _PERIOD_KEYWORDS.items():
        if _tags_include(proposed_tags, variants) and not _prose_mentions(prose, variants):
            warnings.append(
                f"Tag “{canonical}” is not supported by the existing comments."
            )
    return warnings
