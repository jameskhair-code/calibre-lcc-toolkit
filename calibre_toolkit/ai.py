"""
AI client (Anthropic-only).

Books are sent in batches and processed concurrently to minimise wall time.
The system prompt for each command is cached via Anthropic prompt caching so
that successive batches in the same run pay near-zero for the (large) rules
file portion of the prompt.
"""

from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from .db import Book, BookDetails
from .logging_config import get_logger
from .models import resolve_model
from .normalize import normalize_text
from .schemas import (
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

_log = get_logger(__name__)

# Rules file lives alongside the package root
_RULES_DIR = Path(__file__).parent.parent / "rules"


def _load_rules(rules_file: str) -> str:
    path = _RULES_DIR / rules_file
    if not path.exists():
        raise FileNotFoundError(
            f"Rules file not found: {path}\n"
            "Expected rules/ directory alongside the calibre_toolkit package."
        )
    return path.read_text(encoding="utf-8")


# ── Shared JSON extraction ──────────────────────────────────────────────────
#
# Models occasionally wrap output in ```json fences, prepend a sentence of
# commentary, or trail explanation after the closing bracket. Rather than
# defending against each variant, find the outermost array (or object) and
# parse exactly that substring.

def _extract_json_array(raw: str) -> list:
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(f"AI returned no JSON array.\n\nRaw response:\n{raw[:1000]}")
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"AI returned invalid JSON: {e}\n\nRaw response:\n{raw[:1000]}")


def _extract_json_object(raw: str) -> dict:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(f"AI returned no JSON object.\n\nRaw response:\n{raw[:1000]}")
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"AI returned invalid JSON: {e}\n\nRaw response:\n{raw[:1000]}")


# ── Data classes ────────────────────────────────────────────────────────────

SourceAuthority = Literal[
    "lc_catalog",
    "worldcat_consensus",
    "open_library",
    "ai_inference",
]

_SOURCE_AUTHORITY_VALUES: frozenset[str] = frozenset({
    "lc_catalog", "worldcat_consensus", "open_library", "ai_inference",
})

_ATTRIBUTION_PREFIX = {
    "lc_catalog":         "[LC]",
    "worldcat_consensus": "[WC]",
    "open_library":       "[OL]",
    "ai_inference":       "[AI]",
}


@dataclass
class LccSuggestion:
    book_id: int
    title: str
    authors: list[str]
    current: dict[str, str]
    proposed: dict[str, str]
    confidence: Literal["high", "medium", "low"]
    source: str = ""
    notes: str = ""
    parse_error: str = ""
    # Structural provenance. The AI returns it as a hint; the parser
    # downgrades any unsupported claim to "ai_inference" (see
    # _normalise_lcc_source_authority). Catalog-built suggestions
    # populate this directly in _build_catalog_suggestion.
    source_authority: SourceAuthority = "ai_inference"

    @property
    def authors_display(self) -> str:
        return " & ".join(self.authors)

    @property
    def any_change(self) -> bool:
        return any(
            self.proposed.get(k, "") != self.current.get(k, "")
            for k in ("lcc", "lcc_primary_class", "lcc_secondary_class", "lcc_summary")
        )

    @property
    def attribution_prefix(self) -> str:
        """Display prefix derived purely from source_authority — never from
        the AI's free-text source string. Reviewers and the audit log can
        rely on this to distinguish AI-only rows from catalog-confirmed ones.
        """
        return _ATTRIBUTION_PREFIX.get(self.source_authority, "[AI]")


@dataclass
class TagOperation:
    source_tags: list[str]
    target_tags: list[str]
    reason: str
    book_count: int = 0
    pattern_group: str = "ai-semantic"

    @property
    def kind(self) -> str:
        if not self.target_tags:
            return "drop"
        if len(self.source_tags) == 1 and len(self.target_tags) == 1:
            return "rename" if self.source_tags[0] != self.target_tags[0] else "noop"
        if len(self.source_tags) > 1 and len(self.target_tags) == 1:
            return "merge"
        if len(self.source_tags) == 1 and len(self.target_tags) > 1:
            return "split"
        return "rewrite"

    @property
    def display_arrow(self) -> str:
        sources = ", ".join(self.source_tags)
        if not self.target_tags:
            return f"{sources} → (drop)"
        if len(self.target_tags) > 1:
            targets = " + ".join(self.target_tags)
        else:
            targets = self.target_tags[0]
        return f"{sources} → {targets}"


@dataclass
class TagsSuggestion:
    book_id: int
    title: str
    authors: list[str]
    current_tags: list[str]
    proposed_tags: list[str]
    confidence: Literal["high", "medium", "low"]
    notes: str = ""
    parse_error: str = ""

    @property
    def authors_display(self) -> str:
        return " & ".join(self.authors)

    @property
    def tags_changed(self) -> bool:
        return sorted(self.proposed_tags) != sorted(self.current_tags)

    @property
    def kept(self) -> list[str]:
        proposed_lower = {t.lower() for t in self.proposed_tags}
        return [t for t in self.current_tags if t.lower() in proposed_lower]

    @property
    def added(self) -> list[str]:
        current_lower = {t.lower() for t in self.current_tags}
        return [t for t in self.proposed_tags if t.lower() not in current_lower]

    @property
    def removed(self) -> list[str]:
        proposed_lower = {t.lower() for t in self.proposed_tags}
        return [t for t in self.current_tags if t.lower() not in proposed_lower]


@dataclass
class TagsReviewSuggestion:
    book_id: int
    title: str
    authors: list[str]
    current_tags: list[str]
    proposed_tags: list[str]
    assessment: Literal["complete", "needs_additions", "needs_corrections"]
    confidence: Literal["high", "medium", "low"]
    notes: str = ""
    parse_error: str = ""

    @property
    def authors_display(self) -> str:
        return " & ".join(self.authors)

    @property
    def kept(self) -> list[str]:
        proposed_lower = {t.lower() for t in self.proposed_tags}
        return [t for t in self.current_tags if t.lower() in proposed_lower]

    @property
    def added(self) -> list[str]:
        current_lower = {t.lower() for t in self.current_tags}
        return [t for t in self.proposed_tags if t.lower() not in current_lower]

    @property
    def removed(self) -> list[str]:
        proposed_lower = {t.lower() for t in self.proposed_tags}
        return [t for t in self.current_tags if t.lower() not in proposed_lower]


@dataclass
class CommentsSuggestion:
    book_id: int
    title: str
    authors: list[str]
    book_type: Literal["fiction", "nonfiction", ""]
    sections: dict[str, str]
    must_read_score: int
    must_read_rationale: str
    html: str
    confidence: Literal["high", "medium", "low"]
    notes: str = ""
    parse_error: str = ""

    @property
    def authors_display(self) -> str:
        return " & ".join(self.authors)


@dataclass
class CleanupSuggestion:
    book_id: int
    original_title: str
    original_authors: list[str]
    suggested_title: str
    suggested_authors: list[str]
    confidence: Literal["high", "medium", "low"]
    title_changed: bool
    authors_changed: bool
    notes: str = ""

    @property
    def any_change(self) -> bool:
        return self.title_changed or self.authors_changed

    @property
    def original_authors_display(self) -> str:
        return " & ".join(self.original_authors)

    @property
    def suggested_authors_display(self) -> str:
        return " & ".join(self.suggested_authors)


# ── Prompts ─────────────────────────────────────────────────────────────────

_PROMPT_PREAMBLE = """\
You are a metadata librarian specialising in literary fiction and award-winning books.
Your job is to clean book titles and author names for a Calibre library called
"Collection – Literary Awards and Nominees".

Apply the rules below exactly. When no rule applies, leave the field unchanged.
"""

_PROMPT_OUTPUT_FORMAT = """\

---
## OUTPUT FORMAT

Respond with a JSON array, one object per book, in the SAME ORDER as the input.
Each object must have exactly these keys:
{
  "id": <integer>,
  "title": "<cleaned title>",
  "authors": ["<First Last>", ...],
  "confidence": "high" | "medium" | "low",
  "notes": "<one sentence explaining what was changed and why>"
}

Notes guidance:
- If you made changes: describe specifically what you changed and which rule applies.
  Good: "Removed generic subtitle per T-SUB-02."
  Good: "Lowercased preposition 'with' per title case rules."
  Good: "Removed series parenthetical '(The Way Book 1)' per T-SER-02."
- If you made NO changes: write "Already correctly formatted."
- NEVER write "No changes needed" if you actually changed the title or authors.
- Keep notes to one clear sentence.

Return ONLY the JSON array. No markdown fences, no explanation outside the array.
"""


def _build_system_prompt(rules_file: str = "author_title.md") -> str:
    rules = _load_rules(rules_file)
    return _PROMPT_PREAMBLE + "\n" + rules + "\n" + _PROMPT_OUTPUT_FORMAT


def _build_user_message(books: list[Book]) -> str:
    payload = [
        {
            "id": b.id,
            "title": b.title,
            "authors": b.authors,
        }
        for b in books
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _transform_cleanup_items(
    items: list[CleanupItem],
    books: list[Book],
) -> list[CleanupSuggestion]:
    book_map = {b.id: b for b in books}
    suggestions: list[CleanupSuggestion] = []
    for item in items:
        book_id = item.id
        book = book_map.get(book_id)
        if book is None:
            continue

        raw_title = (item.title or book.title).strip()
        raw_authors: list[str] = []
        for a in (item.authors or book.authors):
            if ";" in a:
                raw_authors.extend(x.strip() for x in a.split(";") if x.strip())
            else:
                raw_authors.append(a.strip())

        suggested_title = normalize_text(raw_title)
        suggested_authors = [normalize_text(a) for a in raw_authors]

        ai_changed_title = raw_title != book.title
        ai_changed_authors = raw_authors != book.authors
        code_changed_title = suggested_title != raw_title
        code_changed_authors = any(n != r for n, r in zip(suggested_authors, raw_authors))

        title_changed = suggested_title != book.title
        authors_changed = suggested_authors != book.authors

        notes = item.notes or ""
        _notes_lower = notes.lower().strip(".").strip()
        no_changes_note = _notes_lower in ("no changes needed", "already correctly formatted")

        if (title_changed or authors_changed) and no_changes_note:
            if not ai_changed_title and not ai_changed_authors:
                parts = []
                if code_changed_title:
                    parts.append("title")
                if code_changed_authors:
                    parts.append("authors")
                notes = f"Americanized special characters in {' and '.join(parts)} (diacritics and dashes converted to plain ASCII)."
            else:
                parts = []
                if title_changed:
                    parts.append("title")
                if authors_changed:
                    parts.append("authors")
                notes = f"Corrected {' and '.join(parts)} formatting."

        suggestions.append(CleanupSuggestion(
            book_id=book_id,
            original_title=book.title,
            original_authors=book.authors,
            suggested_title=suggested_title,
            suggested_authors=suggested_authors,
            confidence=item.confidence,
            title_changed=title_changed,
            authors_changed=authors_changed,
            notes=notes,
        ))
    return suggestions


def _parse_response(raw: str, books: list[Book]) -> list[CleanupSuggestion]:
    """Backward-compatible wrapper: validate + transform in one call."""
    return _transform_cleanup_items(validate_cleanup(raw), books)


# ── AIClient ────────────────────────────────────────────────────────────────


@dataclass
class BatchFailure:
    """One AI batch that failed to return parseable output."""
    batch_index: int
    book_ids: list[int]
    error: str


class AIClient:
    """Anthropic-only client with batch concurrency and prompt caching.

    `max_concurrency` controls how many in-flight requests run at once for
    multi-batch suggest_* calls. The Anthropic SDK is thread-safe.
    """

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        max_concurrency: int = 5,
        request_timeout_seconds: float = 120.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        resolved = resolve_model(model)
        self.model = resolved.model_id
        self.model_alias = resolved.alias
        self.max_concurrency = max_concurrency
        self.request_timeout_seconds = request_timeout_seconds
        self.max_retries = max_retries
        self._client = None
        # Populated by the last suggest_* call so callers can surface failures.
        self.last_failures: list[BatchFailure] = []

    def _anthropic(self):
        if self._client is None:
            from anthropic import Anthropic
            # max_retries handles transient 429/5xx with built-in backoff.
            self._client = Anthropic(
                api_key=self.api_key,
                max_retries=self.max_retries,
                timeout=self.request_timeout_seconds,
            )
        return self._client

    def _call_with_validation(
        self,
        user_msg: str,
        system_prompt: str,
        validator: Callable[[str], object],
        max_tokens: int = 8192,
    ) -> object:
        """Call the model and validate the response shape. Retries once with
        a targeted correction prompt on the first SchemaViolation; re-raises
        on the second.

        validator is one of the `validate_*` helpers in `schemas.py`; it returns
        the parsed Pydantic object(s) on success or raises SchemaViolation.
        """
        raw = self._call(user_msg, system_prompt, max_tokens=max_tokens)
        try:
            return validator(raw)
        except SchemaViolation as first_err:
            _log.warning(
                "AI response failed schema validation; retrying with correction prompt: %s",
                str(first_err).splitlines()[0] if str(first_err) else "(no detail)",
            )
            correction = build_correction_prompt(user_msg, first_err)
            raw2 = self._call(correction, system_prompt, max_tokens=max_tokens)
            try:
                return validator(raw2)
            except SchemaViolation as second_err:
                _log.error(
                    "AI response failed schema validation twice in a row; "
                    "surfacing failure to caller. error=%s",
                    str(second_err).splitlines()[0] if str(second_err) else "(no detail)",
                )
                raise

    def _call(self, user_msg: str, system_prompt: str, max_tokens: int = 8192) -> str:
        """Single Anthropic call with prompt caching on the system block."""
        response = self._anthropic().messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
        )
        return response.content[0].text.strip()

    def _run_batches_concurrent(
        self,
        fn: Callable[[list], list],
        batches: list[list],
        progress_callback: Callable[[int, int, int], None] | None = None,
    ) -> list:
        """Run `fn(batch)` for each batch concurrently. Returns flat list of
        results from successful batches. Failures are stored on self.last_failures.

        progress_callback(completed, total, failed) is called after each batch.
        """
        self.last_failures = []
        results: list = []
        # Map: future → (batch_index, batch)
        with ThreadPoolExecutor(max_workers=self.max_concurrency) as pool:
            futures = {
                pool.submit(fn, batch): (idx, batch)
                for idx, batch in enumerate(batches)
            }
            completed = 0
            for fut in as_completed(futures):
                idx, batch = futures[fut]
                try:
                    results.extend(fut.result())
                except Exception as e:
                    book_ids = [getattr(b, "id", b.get("id") if isinstance(b, dict) else 0) for b in batch]
                    self.last_failures.append(BatchFailure(
                        batch_index=idx,
                        book_ids=book_ids,
                        error=str(e),
                    ))
                completed += 1
                if progress_callback:
                    progress_callback(completed, len(batches), len(self.last_failures))
        return results

    # ── Clean-titles ──────────────────────────────────────────────────────

    def suggest_cleanup(
        self,
        books: list[Book],
        batch_size: int = 50,
        progress_callback: Callable[[int, int, int], None] | None = None,
    ) -> list[CleanupSuggestion]:
        if not books:
            return []
        batches = [books[i : i + batch_size] for i in range(0, len(books), batch_size)]
        return self._run_batches_concurrent(self._process_batch, batches, progress_callback)

    def _process_batch(self, books: list[Book]) -> list[CleanupSuggestion]:
        user_msg = _build_user_message(books)
        system_prompt = _build_system_prompt("author_title.md")
        items = self._call_with_validation(
            user_msg, system_prompt, validate_cleanup, max_tokens=8192,
        )
        return _transform_cleanup_items(items, books)

    # ── LCC ───────────────────────────────────────────────────────────────

    def suggest_lcc(
        self,
        books: list[Book],
        current_map: dict[int, dict[str, str]],
        batch_size: int = 10,
        progress_callback: Callable[[int, int, int], None] | None = None,
    ) -> list[LccSuggestion]:
        if not books:
            return []
        batches = [books[i : i + batch_size] for i in range(0, len(books), batch_size)]

        def _run(batch):
            return self._process_lcc_batch(batch, current_map)

        return self._run_batches_concurrent(_run, batches, progress_callback)

    def _process_lcc_batch(
        self,
        books: list[Book],
        current_map: dict[int, dict[str, str]],
    ) -> list[LccSuggestion]:
        system_prompt = _build_lcc_system_prompt()
        user_msg = _build_lcc_user_message(books, current_map)
        items = self._call_with_validation(
            user_msg, system_prompt, validate_lcc, max_tokens=8192,
        )
        return _transform_lcc_items(items, books, current_map)

    # ── Tags-review (single book, no batching) ────────────────────────────

    def suggest_tags_review(
        self,
        book: Book,
        current_tags: list[str],
        description: str = "",
        series: str = "",
        year: str = "",
        publisher: str = "",
        lcc_summary: str = "",
        lcc_primary: str = "",
        lcc_secondary: str = "",
    ) -> TagsReviewSuggestion:
        user_msg = _build_tags_review_user_message(
            book, current_tags, description, series, year, publisher,
            lcc_summary, lcc_primary, lcc_secondary,
        )
        try:
            obj = self._call_with_validation(
                user_msg, _TAGS_REVIEW_SYSTEM_PROMPT,
                validate_tags_review, max_tokens=1024,
            )
        except SchemaViolation as e:
            return TagsReviewSuggestion(
                book_id=book.id, title=book.title, authors=book.authors,
                current_tags=list(current_tags), proposed_tags=list(current_tags),
                assessment="complete", confidence="low",
                parse_error=str(e)[:200],
            )
        return _transform_tags_review_item(obj, book, current_tags)

    # ── Tag-cleanup (single big call, no batching) ────────────────────────

    def suggest_tag_cleanup(
        self,
        tags: list[tuple[str, int]],
        batch_size: int = 150,
        progress_callback: Callable[[int, int, int], None] | None = None,
    ) -> list[TagOperation]:
        if not tags:
            return []
        system_prompt = _build_tag_cleanup_system_prompt()
        count_map = {t: c for t, c in tags}
        # Sort case-insensitively so near-duplicates and variant spellings
        # ("Sci-Fi", "Sci Fi", "Science Fiction") tend to land in the same
        # batch and remain mergeable.
        sorted_tags = sorted(tags, key=lambda x: x[0].lower())
        batches = [
            sorted_tags[i : i + batch_size]
            for i in range(0, len(sorted_tags), batch_size)
        ]

        def _run(batch: list[tuple[str, int]]) -> list[TagOperation]:
            user_msg = _build_tag_cleanup_user_message(batch)
            ops = self._call_with_validation(
                user_msg, system_prompt, validate_tag_cleanup, max_tokens=8192,
            )
            return _transform_tag_cleanup_ops(ops, count_map)

        return self._run_batches_concurrent(_run, batches, progress_callback)

    # ── Tags (batch) ──────────────────────────────────────────────────────

    def suggest_tags(
        self,
        books: list[Book],
        tags_map: dict[int, list[str]],
        context_map: dict[int, dict[str, str]] | None = None,
        batch_size: int = 20,
        progress_callback: Callable[[int, int, int], None] | None = None,
    ) -> list[TagsSuggestion]:
        if not books:
            return []
        ctx = context_map or {}
        batches = [books[i : i + batch_size] for i in range(0, len(books), batch_size)]

        def _run(batch):
            return self._process_tags_batch(batch, tags_map, ctx)

        return self._run_batches_concurrent(_run, batches, progress_callback)

    def _process_tags_batch(
        self,
        books: list[Book],
        tags_map: dict[int, list[str]],
        context_map: dict[int, dict[str, str]],
    ) -> list[TagsSuggestion]:
        system_prompt = _build_tags_system_prompt()
        user_msg = _build_tags_user_message(books, tags_map, context_map)
        items = self._call_with_validation(
            user_msg, system_prompt, validate_tags, max_tokens=8192,
        )
        return _transform_tags_items(items, books, tags_map)

    # ── Comments (batch) ──────────────────────────────────────────────────

    def suggest_comments(
        self,
        books: list[Book],
        details_map: dict[int, BookDetails],
        lcc_summary_map: dict[int, str] | None = None,
        batch_size: int = 5,
        progress_callback: Callable[[int, int, int], None] | None = None,
    ) -> list[CommentsSuggestion]:
        if not books:
            return []
        batches = [books[i : i + batch_size] for i in range(0, len(books), batch_size)]

        def _run(batch):
            return self._process_comments_batch(batch, details_map, lcc_summary_map)

        return self._run_batches_concurrent(_run, batches, progress_callback)

    def _process_comments_batch(
        self,
        books: list[Book],
        details_map: dict[int, BookDetails],
        lcc_summary_map: dict[int, str] | None = None,
    ) -> list[CommentsSuggestion]:
        system_prompt = _build_comments_system_prompt()
        user_msg = _build_comments_user_message(books, details_map, lcc_summary_map)
        items = self._call_with_validation(
            user_msg, system_prompt, validate_comments, max_tokens=8192,
        )
        return _transform_comments_items(items, books)


# ── LCC prompt + parsing ─────────────────────────────────────────────────────

_LCC_PROMPT_PREAMBLE = """\
You are a metadata librarian propagating Library of Congress Classification (LCC)
values into a personal Calibre library called "Collection – Literary Awards
and Nominees".

For each book, propose four LCC fields plus confidence, source, and notes.
Apply the rules below exactly. Prefer catalog evidence over invention.
"""

_LCC_PROMPT_OUTPUT_FORMAT = """\

---
## OUTPUT FORMAT

Respond with a JSON array, one object per book, in the SAME ORDER as the input.
Each object must have exactly these keys:
{
  "id": <integer>,
  "lcc": "<LCC call number, or empty string>",
  "lcc_primary_class": "<exact canonical drop-down string from PRI-02>",
  "lcc_secondary_class": "<exact canonical drop-down string from SEC-05>",
  "lcc_summary": "<one-sentence subject summary per PATH section — plain prose, 20–40 words>",
  "confidence": "high" | "medium" | "low",
  "source_authority": "lc_catalog" | "worldcat_consensus" | "open_library" | "ai_inference",
  "source": "<short phrase describing the strongest evidence used>",
  "notes": "<one short sentence; reasoning or caveat>"
}

source_authority semantics — see SRC-06 in the rules:
  - "lc_catalog"         only if you can cite a specific LC record (LCCN or ISBN).
  - "worldcat_consensus" only if you can cite multiple library catalog records.
  - "open_library"       only if you can cite an OL bibkey/work.
  - "ai_inference"       otherwise — including all reasoning from training data,
                         topic inference, or schedule-derived classification.

You are being called as a fallback for books that already failed direct catalog
lookups. Return "ai_inference" unless you can cite a specific catalog record.

Return ONLY the JSON array. No markdown fences, no commentary outside the array.
"""


def _build_lcc_system_prompt() -> str:
    rules = _load_rules("lcc.md")
    return _LCC_PROMPT_PREAMBLE + "\n" + rules + "\n" + _LCC_PROMPT_OUTPUT_FORMAT


def _build_lcc_user_message(books: list[Book], current_map: dict[int, dict[str, str]]) -> str:
    payload = []
    for b in books:
        current = current_map.get(b.id, {})
        item = {
            "id": b.id,
            "title": b.title,
            "authors": b.authors,
        }
        if any(current.get(k) for k in ("lcc", "lcc_primary_class", "lcc_secondary_class", "lcc_summary")):
            item["current"] = {k: current.get(k, "") for k in
                               ("lcc", "lcc_primary_class", "lcc_secondary_class", "lcc_summary")}
        payload.append(item)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _normalise_lcc_source_authority(
    raw_value: object,
    notes: str,
) -> tuple[SourceAuthority, str]:
    """Enforce the source_authority contract documented in SRC-06.

    The AI is called only after direct catalog lookups have already missed,
    so any `lc_catalog` or `worldcat_consensus` claim it returns cannot be
    structurally verified by us and is downgraded to `ai_inference` with a
    visible note appended.

    Returns (normalised_authority, normalised_notes).
    """
    value = (str(raw_value) if raw_value is not None else "").strip().lower()
    if value not in _SOURCE_AUTHORITY_VALUES:
        return "ai_inference", notes

    if value in ("lc_catalog", "worldcat_consensus"):
        suffix = (
            f"AI claimed source_authority={value!r} but no catalog hit was "
            "passed in; downgraded to ai_inference."
        )
        new_notes = f"{notes} {suffix}".strip() if notes else suffix
        return "ai_inference", new_notes

    # open_library and ai_inference pass through as-is.
    return value, notes  # type: ignore[return-value]


def _transform_lcc_items(
    items: list[LccItem],
    books: list[Book],
    current_map: dict[int, dict[str, str]],
) -> list[LccSuggestion]:
    book_map = {b.id: b for b in books}
    suggestions: list[LccSuggestion] = []
    for item in items:
        book = book_map.get(item.id)
        if book is None:
            continue
        proposed = {
            "lcc": item.lcc.strip(),
            "lcc_primary_class": item.lcc_primary_class.strip(),
            "lcc_secondary_class": item.lcc_secondary_class.strip(),
            "lcc_summary": item.lcc_summary.strip(),
        }
        notes = item.notes.strip()
        authority, notes = _normalise_lcc_source_authority(
            item.source_authority, notes,
        )
        suggestions.append(LccSuggestion(
            book_id=item.id,
            title=book.title,
            authors=book.authors,
            current=current_map.get(item.id, {}),
            proposed=proposed,
            confidence=item.confidence,
            source=item.source.strip(),
            notes=notes,
            source_authority=authority,
        ))
    return suggestions


def _parse_lcc_response(
    raw: str,
    books: list[Book],
    current_map: dict[int, dict[str, str]],
) -> list[LccSuggestion]:
    return _transform_lcc_items(validate_lcc(raw), books, current_map)


# ── Comments prompt + parsing ─────────────────────────────────────────────────

# Prose sections rendered in HTML, in display order. Empty values are skipped,
# so the fiction/non-fiction split is handled implicitly — the AI returns empty
# strings for the keys that do not apply to the book's type.
_COMMENTS_SECTION_KEYS = [
    ("the_book",                     "The Book"),                  # non-fiction
    ("the_story",                    "The Story"),                 # fiction
    ("the_argument",                 "The Argument"),              # non-fiction
    ("what_its_really_about",        "What It's Really About"),    # fiction
    ("something_you_might_not_know", "Something You Might Not Know"),
    ("why_read_it",                  "Why Read It"),
]

_COMMENTS_PROMPT_PREAMBLE = """\
You are a metadata librarian generating book descriptions for a personal Calibre
library called "Collection – Literary Awards and Nominees". The reader profile
and structural rules below define what to write and how. Apply them to every book.
"""

_COMMENTS_OUTPUT_FORMAT = """\

---
## OUTPUT FORMAT

Respond with a JSON array, one object per book, in the SAME ORDER as the input.
Each object must have exactly these keys:
{
  "id": <integer>,
  "book_type": "fiction" | "nonfiction",
  "the_book":              "<plain prose — non-fiction only; empty string for fiction>",
  "the_argument":          "<plain prose — non-fiction only; empty string for fiction>",
  "the_story":             "<plain prose — fiction only; empty string for non-fiction>",
  "what_its_really_about": "<plain prose — fiction only; empty string for non-fiction>",
  "something_you_might_not_know": "<plain prose, or empty string if nothing noteworthy>",
  "why_read_it":           "<plain prose — no HTML tags>",
  "must_read_score":       <integer 0–10>,
  "must_read_rationale":   "<1–2 sentences>",
  "confidence":            "high" | "medium" | "low",
  "notes":                 "<one short sentence — main caveat or key evidence>"
}

Return ONLY the JSON array. No markdown fences, no commentary outside the array.
"""


def _build_comments_system_prompt() -> str:
    reader_profile = _load_rules("reader_profile.md")
    comments_rules = _load_rules("comments.md")

    return (
        _COMMENTS_PROMPT_PREAMBLE
        + "\n\n## READER PROFILE\n\n"
        + reader_profile
        + "\n\n## STRUCTURAL RULES\n\n"
        + comments_rules
        + _COMMENTS_OUTPUT_FORMAT
    )


def _build_comments_user_message(
    books: list[Book],
    details_map: dict[int, BookDetails],
    lcc_summary_map: dict[int, str] | None = None,
) -> str:
    payload = []
    for b in books:
        d = details_map.get(b.id)
        item: dict = {"id": b.id, "title": b.title, "authors": b.authors}
        if d:
            if d.tags:
                item["tags"] = d.tags
            if d.series:
                item["series"] = d.series
            if d.pubdate:
                item["pubdate"] = d.pubdate
            if d.publisher:
                item["publisher"] = d.publisher
            if d.existing_comments:
                item["existing_comments"] = d.existing_comments[:600]
        if lcc_summary_map:
            lcc_s = lcc_summary_map.get(b.id, "")
            if lcc_s:
                item["lcc_summary"] = lcc_s
        payload.append(item)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _format_comments_html(
    sections: dict[str, str],
    score: int | None = None,
    rationale: str = "",
) -> str:
    parts = []
    for key, label in _COMMENTS_SECTION_KEYS:
        text = (sections.get(key) or "").strip()
        if not text:
            continue
        parts.append(f"<h3>{label}</h3>\n<p>{text}</p>")
    if score is not None:
        rationale_html = f" — {rationale}" if rationale else ""
        parts.append(
            f"<h3>Must-Read</h3>\n<p><strong>{score} / 10</strong>{rationale_html}</p>"
        )
    return "\n".join(parts)


def _coerce_score(value) -> int | None:
    """Best-effort coercion of the AI's score to an int in [0, 10]."""
    if value is None or value == "":
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(10, n))


def _transform_comments_items(
    items: list[CommentsItem],
    books: list[Book],
) -> list[CommentsSuggestion]:
    book_map = {b.id: b for b in books}
    suggestions: list[CommentsSuggestion] = []
    for item in items:
        book = book_map.get(item.id)
        if book is None:
            continue
        section_data = {
            "the_book": item.the_book,
            "the_argument": item.the_argument,
            "the_story": item.the_story,
            "what_its_really_about": item.what_its_really_about,
            "something_you_might_not_know": item.something_you_might_not_know,
            "why_read_it": item.why_read_it,
        }
        sections = {key: (section_data.get(key) or "").strip() for key, _ in _COMMENTS_SECTION_KEYS}
        book_type = item.book_type if item.book_type in ("fiction", "nonfiction") else ""
        score = _coerce_score(item.must_read_score)
        rationale = (item.must_read_rationale or "").strip()
        suggestions.append(CommentsSuggestion(
            book_id=item.id,
            title=book.title,
            authors=book.authors,
            book_type=book_type,
            sections=sections,
            must_read_score=score if score is not None else -1,
            must_read_rationale=rationale,
            html=_format_comments_html(sections, score, rationale),
            confidence=item.confidence,
            notes=(item.notes or "").strip(),
        ))
    return suggestions


def _parse_comments_response(raw: str, books: list[Book]) -> list[CommentsSuggestion]:
    return _transform_comments_items(validate_comments(raw), books)


# ── Tags prompt + parsing ─────────────────────────────────────────────────────

_TAGS_PROMPT_PREAMBLE = """\
You are a metadata librarian generating subject tags for a personal Calibre
library called "Collection – Literary Awards and Nominees". Tags are the
primary search surface — accuracy and consistency matter more than
comprehensiveness. Apply the rules below exactly.
"""

_TAGS_OUTPUT_FORMAT = """\

---
## OUTPUT FORMAT

Respond with a JSON array, one object per book, in the SAME ORDER as the input.
Each object must have exactly these keys:
{
  "id": <integer>,
  "tags": ["Tag One", "Tag Two", ...],
  "confidence": "high" | "medium" | "low",
  "notes": "<one short sentence>"
}

"tags" is a flat array of 4–8 plain strings. No category prefixes, no nesting.
No commas within any tag string.
Return ONLY the JSON array. No markdown fences, no commentary outside the array.
"""


def _build_tags_system_prompt() -> str:
    rules = _load_rules("tags.md")
    return _TAGS_PROMPT_PREAMBLE + "\n" + rules + _TAGS_OUTPUT_FORMAT


def _build_tags_user_message(
    books: list[Book],
    tags_map: dict[int, list[str]],
    context_map: dict[int, dict[str, str]],
) -> str:
    payload = []
    for b in books:
        item: dict = {"id": b.id, "title": b.title, "authors": b.authors}
        ctx = context_map.get(b.id, {})
        if ctx.get("lcc_primary_class"):
            item["lcc_primary_class"] = ctx["lcc_primary_class"]
        if ctx.get("lcc_secondary_class"):
            item["lcc_secondary_class"] = ctx["lcc_secondary_class"]
        if ctx.get("lcc_summary"):
            item["lcc_summary"] = ctx["lcc_summary"]
        current = tags_map.get(b.id, [])
        if current:
            item["current_tags"] = current
        payload.append(item)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_tag_cleanup_system_prompt() -> str:
    preamble = (
        "You are a metadata librarian normalizing the tag vocabulary of a "
        "personal Calibre library called “Collection – Literary Awards and "
        "Nominees”. Below is the current list of all tags with how many books "
        "use each. Apply the rules that follow exactly.\n\n"
    )
    return preamble + _load_rules("tags_cleanup.md")


def _build_tag_cleanup_user_message(tags: list[tuple[str, int]]) -> str:
    lines = [f"{name} ({count} book{'s' if count != 1 else ''})" for name, count in tags]
    return "Current tag vocabulary:\n\n" + "\n".join(lines)


def _transform_tag_cleanup_ops(
    raw_ops: list[TagCleanupOp],
    counts: dict[str, int],
) -> list[TagOperation]:
    ops: list[TagOperation] = []
    for raw_op in raw_ops:
        sources = [t.strip() for t in raw_op.source_tags if t.strip()]
        targets = [t.strip() for t in raw_op.target_tags if t.strip()]
        reason = (raw_op.reason or "").strip()
        reason_words = reason.split()
        if len(reason_words) > 10:
            reason = " ".join(reason_words[:10])
        if not sources:
            continue
        if len(sources) == 1 and len(targets) == 1 and sources[0] == targets[0]:
            continue
        total = sum(counts.get(t, 0) for t in sources)
        ops.append(TagOperation(
            source_tags=sources,
            target_tags=targets,
            reason=reason,
            book_count=total,
            pattern_group="ai-semantic",
        ))
    return ops


def _parse_tag_cleanup_response(
    raw: str,
    counts: dict[str, int],
) -> list[TagOperation]:
    return _transform_tag_cleanup_ops(validate_tag_cleanup(raw), counts)


# ── Tags Review prompt + parsing ─────────────────────────────────────────────

_TAGS_REVIEW_SYSTEM_PROMPT = """\
You are a metadata librarian assessing subject tags for a personal Calibre library
called "Collection – Literary Awards and Nominees".

Given a single book's full metadata — title, authors, description, current tags,
and Library of Congress classification — assess whether the current tags are
complete and accurate, then propose the ideal final tag set.

Tag rules:
- 4–8 flat tags per book. No prefixes, no nesting, no category labels.
- Four implicit categories (use the values, not the category names as prefixes):
  • Form     — Novel, Biography, Memoir, Short Stories, Poetry, Nonfiction, etc.
  • Subject  — What the book is about (Military History, Cold War, Immigration, etc.)
  • Period   — Historical period if central (World War II, Victorian Era, etc.)
  • Geography — Region if central (United States, Russia, Sub-Saharan Africa, etc.)
- Preserve sub-genre specificity: "Space Opera" ≠ "Science Fiction";
  "Literary Fiction" ≠ "Fiction"; "Historical Mystery" ≠ "Mystery"
- Avoid over-general tags that add no value ("Book", "Read", "Literature")
- Assessment values:
  • "complete"           — current tags are accurate and sufficient; no change needed
  • "needs_additions"    — good base but missing important tags; keep current + add
  • "needs_corrections"  — current tags have inaccurate or noisy entries to replace

---
## OUTPUT FORMAT

Respond with a single JSON object (NOT an array):
{
  "assessment": "complete" | "needs_additions" | "needs_corrections",
  "proposed_tags": ["Tag1", "Tag2", ...],
  "confidence": "high" | "medium" | "low",
  "notes": "<one sentence: what changed and why, or confirming completeness>"
}

Return ONLY the JSON object. No markdown fences, no commentary.
"""


def _build_tags_review_user_message(
    book: Book,
    current_tags: list[str],
    description: str,
    series: str,
    year: str,
    publisher: str,
    lcc_summary: str,
    lcc_primary: str,
    lcc_secondary: str,
) -> str:
    item: dict = {"id": book.id, "title": book.title, "authors": book.authors}
    if year:
        item["year"] = year
    if series:
        item["series"] = series
    if publisher:
        item["publisher"] = publisher
    if current_tags:
        item["current_tags"] = current_tags
    if description:
        item["description"] = description[:800]
    if lcc_summary:
        item["lcc_summary"] = lcc_summary
    if lcc_primary:
        item["lcc_primary_class"] = lcc_primary
    if lcc_secondary:
        item["lcc_secondary_class"] = lcc_secondary
    return json.dumps(item, ensure_ascii=False, indent=2)


def _transform_tags_review_item(
    obj: TagsReviewResponse,
    book: Book,
    current_tags: list[str],
) -> TagsReviewSuggestion:
    proposed = [t.strip() for t in obj.proposed_tags if isinstance(t, str) and t.strip()]
    if not proposed:
        proposed = list(current_tags)
    proposed, notes, confidence = _validate_proposed_tags(
        proposed, obj.notes.strip(), obj.confidence,
    )
    return TagsReviewSuggestion(
        book_id=book.id,
        title=book.title,
        authors=book.authors,
        current_tags=list(current_tags),
        proposed_tags=proposed,
        assessment=obj.assessment,
        confidence=confidence,
        notes=notes,
    )


def _parse_tags_review_response(
    raw: str,
    book: Book,
    current_tags: list[str],
) -> TagsReviewSuggestion:
    try:
        obj = validate_tags_review(raw)
    except SchemaViolation as e:
        return TagsReviewSuggestion(
            book_id=book.id, title=book.title, authors=book.authors,
            current_tags=current_tags, proposed_tags=list(current_tags),
            assessment="complete", confidence="low",
            parse_error=str(e)[:200],
        )
    return _transform_tags_review_item(obj, book, current_tags)


_FORM_TAGS = frozenset({
    "Novel", "Short Stories", "Poetry", "Drama", "Memoir",
    "Autobiography", "Biography", "History", "Nonfiction",
    "Essay Collection", "Literary Criticism", "Philosophy",
    "Science", "Political Science", "Journalism",
})


def _validate_proposed_tags(
    proposed: list[str],
    notes: str,
    confidence: str,
) -> tuple[list[str], str, str]:
    """Enforce FORMAT-02 (4-word cap), FORMAT-03 (no commas), FORM-01 (one Form tag)."""
    cleaned = []
    for tag in proposed:
        tag = tag.split(",")[0].strip()  # FORMAT-03: strip at first comma
        words = tag.split()
        if len(words) > 4:              # FORMAT-02: truncate to 4 words
            tag = " ".join(words[:4])
        if tag:
            cleaned.append(tag)

    form_tags = [t for t in cleaned if t in _FORM_TAGS]
    if len(form_tags) != 1:
        confidence = "medium"
        label = ", ".join(form_tags) if form_tags else "none found"
        suffix = f"Form tag issue: {label}."
        notes = f"{notes} {suffix}".strip() if notes else suffix

    return cleaned, notes, confidence


def _transform_tags_items(
    items: list[TagsItem],
    books: list[Book],
    tags_map: dict[int, list[str]],
) -> list[TagsSuggestion]:
    book_map = {b.id: b for b in books}
    suggestions: list[TagsSuggestion] = []
    for item in items:
        book = book_map.get(item.id)
        if book is None:
            continue
        proposed = [t.strip() for t in item.tags if isinstance(t, str) and t.strip()]
        proposed, notes, confidence = _validate_proposed_tags(
            proposed, (item.notes or "").strip(), item.confidence,
        )
        suggestions.append(TagsSuggestion(
            book_id=item.id,
            title=book.title,
            authors=book.authors,
            current_tags=tags_map.get(item.id, []),
            proposed_tags=proposed,
            confidence=confidence,
            notes=notes,
        ))
    return suggestions


def _parse_tags_response(
    raw: str,
    books: list[Book],
    tags_map: dict[int, list[str]],
) -> list[TagsSuggestion]:
    return _transform_tags_items(validate_tags(raw), books, tags_map)
    return suggestions
