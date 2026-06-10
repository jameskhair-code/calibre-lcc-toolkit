"""Shared AI core: the Anthropic client with batch concurrency, prompt
caching, token telemetry, schema-validation retry, and the JSON extractors.

The suggest_* methods stay on AIClient (the public per-step surface) as thin
glue — batch split, builder, validator, transform; the per-step machinery
they call lives in the sibling step modules (authors / lcc / tags / comments).
"""

from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from ..db import Book, BookDetails
from ..logging_config import get_logger
from ..models import resolve_model
from ..usage import UsageAggregate, log_usage, parse_usage

if TYPE_CHECKING:
    from ..services.book_description import BookDescription
from ..schemas import (
    LccSummaryItem,
    SchemaViolation,
    build_correction_prompt,
    validate_cleanup,
    validate_comments,
    validate_lcc,
    validate_lcc_summary,
    validate_tag_cleanup,
    validate_tags,
    validate_tags_review,
)

from .authors import (
    CleanupSuggestion,
    _build_system_prompt,
    _build_user_message,
    _transform_cleanup_items,
)
from .comments import (
    CommentsSuggestion,
    _build_comments_system_prompt,
    _build_comments_user_message,
    _transform_comments_items,
)
from .lcc import (
    LccSuggestion,
    _build_lcc_summary_system_prompt,
    _build_lcc_summary_user_message,
    _build_lcc_system_prompt,
    _build_lcc_user_message,
    _transform_lcc_items,
)
from .tags import (
    TagOperation,
    TagsReviewSuggestion,
    TagsSuggestion,
    _build_tag_cleanup_system_prompt,
    _build_tag_cleanup_user_message,
    _build_tags_review_system_prompt,
    _build_tags_review_user_message,
    _build_tags_system_prompt,
    _build_tags_user_message,
    _transform_tag_cleanup_ops,
    _transform_tags_items,
    _transform_tags_review_item,
)

_log = get_logger(__name__)


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
        step_label: str = "",
    ):
        self.api_key = api_key
        resolved = resolve_model(model)
        self.model = resolved.model_id
        self.model_alias = resolved.alias
        self.max_concurrency = max_concurrency
        self.request_timeout_seconds = request_timeout_seconds
        self.max_retries = max_retries
        # step_label is stamped onto every persisted usage record so a
        # later replay can attribute spend to lcc-enrich / comments-enrich /
        # tags-enrich / etc. without inference.
        self.step_label = step_label
        self._client = None
        # Populated by the last suggest_* call so callers can surface failures.
        self.last_failures: list[BatchFailure] = []
        # Token telemetry (item 13). Accumulates across every _call in this
        # AIClient's lifetime. Read at end-of-step for the summary panel.
        self.usage = UsageAggregate()

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
        # Token telemetry (item 13). Anthropic returns a `usage` block on
        # every successful response. We accumulate into the aggregate so
        # the step module can print a summary at end of run, and we
        # persist one JSONL event so the TUI's overview panel can show
        # cumulative cost across sessions.
        usage = parse_usage(getattr(response, "usage", None))
        self.usage.record(usage, self.model)
        log_usage(usage, self.model, step=self.step_label)
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
        description_map: dict[int, "BookDescription"] | None = None,
    ) -> list[LccSuggestion]:
        if not books:
            return []
        batches = [books[i : i + batch_size] for i in range(0, len(books), batch_size)]

        def _run(batch):
            return self._process_lcc_batch(batch, current_map, description_map or {})

        return self._run_batches_concurrent(_run, batches, progress_callback)

    def _process_lcc_batch(
        self,
        books: list[Book],
        current_map: dict[int, dict[str, str]],
        description_map: dict[int, "BookDescription"] | None = None,
    ) -> list[LccSuggestion]:
        system_prompt = _build_lcc_system_prompt()
        user_msg = _build_lcc_user_message(books, current_map, description_map or {})
        items = self._call_with_validation(
            user_msg, system_prompt, validate_lcc, max_tokens=8192,
        )
        return _transform_lcc_items(items, books, current_map)

    def suggest_lcc_summary(
        self,
        books: list[Book],
        catalog_context_map: dict[int, dict[str, str]],
        description_map: dict[int, "BookDescription"],
        batch_size: int = 10,
        progress_callback: Callable[[int, int, int], None] | None = None,
    ) -> dict[int, str]:
        """v1.7 item 5: AI-generated lcc_summary prose for catalog-hit books.

        Caller supplies the catalog-confirmed lcc/primary/secondary/source
        per book in `catalog_context_map`. Description grounding comes from
        `description_map`. Returns {book_id: lcc_summary} for books the
        model produced non-empty prose for; books with empty AI output
        (identity mismatch) or batch failures are simply absent from the
        result dict and the caller keeps their template summary.
        """
        if not books:
            return {}
        batches = [books[i : i + batch_size] for i in range(0, len(books), batch_size)]

        def _run(batch):
            return self._process_lcc_summary_batch(
                batch, catalog_context_map, description_map,
            )

        rows: list[LccSummaryItem] = self._run_batches_concurrent(
            _run, batches, progress_callback,
        )
        out: dict[int, str] = {}
        for row in rows:
            summary = row.lcc_summary.strip()
            if summary:
                out[row.id] = summary
        return out

    def _process_lcc_summary_batch(
        self,
        books: list[Book],
        catalog_context_map: dict[int, dict[str, str]],
        description_map: dict[int, "BookDescription"],
    ) -> list[LccSummaryItem]:
        system_prompt = _build_lcc_summary_system_prompt()
        user_msg = _build_lcc_summary_user_message(
            books, catalog_context_map, description_map,
        )
        return self._call_with_validation(
            user_msg, system_prompt, validate_lcc_summary, max_tokens=2048,
        )

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
                user_msg, _build_tags_review_system_prompt(),
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
        comments_excerpt_map: dict[int, str] | None = None,
        batch_size: int = 20,
        progress_callback: Callable[[int, int, int], None] | None = None,
    ) -> list[TagsSuggestion]:
        if not books:
            return []
        ctx = context_map or {}
        excerpts = comments_excerpt_map or {}
        batches = [books[i : i + batch_size] for i in range(0, len(books), batch_size)]

        def _run(batch):
            return self._process_tags_batch(batch, tags_map, ctx, excerpts)

        return self._run_batches_concurrent(_run, batches, progress_callback)

    def _process_tags_batch(
        self,
        books: list[Book],
        tags_map: dict[int, list[str]],
        context_map: dict[int, dict[str, str]],
        comments_excerpt_map: dict[int, str],
    ) -> list[TagsSuggestion]:
        system_prompt = _build_tags_system_prompt()
        user_msg = _build_tags_user_message(
            books, tags_map, context_map, comments_excerpt_map,
        )
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
