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
from .normalize import normalize_text

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

    @property
    def authors_display(self) -> str:
        return " & ".join(self.authors)

    @property
    def any_change(self) -> bool:
        return any(
            self.proposed.get(k, "") != self.current.get(k, "")
            for k in ("lcc", "lcc_primary_class", "lcc_secondary_class", "lcc_summary")
        )


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
    sections: dict[str, str]
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


def _parse_response(raw: str, books: list[Book]) -> list[CleanupSuggestion]:
    items = _extract_json_array(raw)
    book_map = {b.id: b for b in books}
    suggestions = []
    for item in items:
        book_id = item["id"]
        book = book_map.get(book_id)
        if book is None:
            continue

        raw_title = item.get("title", book.title).strip()
        raw_authors = []
        for a in item.get("authors", book.authors):
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

        notes = item.get("notes", "")
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
            confidence=item.get("confidence", "medium"),
            title_changed=title_changed,
            authors_changed=authors_changed,
            notes=notes,
        ))
    return suggestions


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
    ):
        self.api_key = api_key
        self.model = model or "claude-sonnet-4-6"
        self.max_concurrency = max_concurrency
        self._client = None
        # Populated by the last suggest_* call so callers can surface failures.
        self.last_failures: list[BatchFailure] = []

    def _anthropic(self):
        if self._client is None:
            from anthropic import Anthropic
            # max_retries handles transient 429/5xx with built-in backoff.
            self._client = Anthropic(api_key=self.api_key, max_retries=3, timeout=120.0)
        return self._client

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
        raw = self._call(user_msg, system_prompt, max_tokens=8192)
        return _parse_response(raw, books)

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
        raw = self._call(user_msg, system_prompt, max_tokens=8192)
        return _parse_lcc_response(raw, books, current_map)

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
        raw = self._call(user_msg, _TAGS_REVIEW_SYSTEM_PROMPT, max_tokens=1024)
        return _parse_tags_review_response(raw, book, current_tags)

    # ── Tag-cleanup (single big call, no batching) ────────────────────────

    def suggest_tag_cleanup(
        self,
        tags: list[tuple[str, int]],
    ) -> list[TagOperation]:
        if not tags:
            return []
        system_prompt = _build_tag_cleanup_system_prompt()
        user_msg = _build_tag_cleanup_user_message(tags)
        raw = self._call(user_msg, system_prompt, max_tokens=16384)
        return _parse_tag_cleanup_response(raw, {t: c for t, c in tags})

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
        raw = self._call(user_msg, system_prompt, max_tokens=8192)
        return _parse_tags_response(raw, books, tags_map)

    # ── Comments (batch) ──────────────────────────────────────────────────

    def suggest_comments(
        self,
        books: list[Book],
        details_map: dict[int, BookDetails],
        lcc_summary_map: dict[int, str] | None = None,
        batch_size: int = 5,
        tone_override: str | None = None,
        progress_callback: Callable[[int, int, int], None] | None = None,
    ) -> list[CommentsSuggestion]:
        if not books:
            return []
        batches = [books[i : i + batch_size] for i in range(0, len(books), batch_size)]

        def _run(batch):
            return self._process_comments_batch(batch, details_map, lcc_summary_map, tone_override)

        return self._run_batches_concurrent(_run, batches, progress_callback)

    def _process_comments_batch(
        self,
        books: list[Book],
        details_map: dict[int, BookDetails],
        lcc_summary_map: dict[int, str] | None = None,
        tone_override: str | None = None,
    ) -> list[CommentsSuggestion]:
        system_prompt = _build_comments_system_prompt(tone_override)
        user_msg = _build_comments_user_message(books, details_map, lcc_summary_map)
        raw = self._call(user_msg, system_prompt, max_tokens=8192)
        return _parse_comments_response(raw, books)


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
  "source": "<short phrase describing the strongest evidence used>",
  "notes": "<one short sentence; reasoning or caveat>"
}

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


def _parse_lcc_response(
    raw: str,
    books: list[Book],
    current_map: dict[int, dict[str, str]],
) -> list[LccSuggestion]:
    items = _extract_json_array(raw)
    book_map = {b.id: b for b in books}
    suggestions: list[LccSuggestion] = []
    for item in items:
        book_id = item.get("id")
        book = book_map.get(book_id)
        if book is None:
            continue
        proposed = {
            "lcc": (item.get("lcc") or "").strip(),
            "lcc_primary_class": (item.get("lcc_primary_class") or "").strip(),
            "lcc_secondary_class": (item.get("lcc_secondary_class") or "").strip(),
            "lcc_summary": (item.get("lcc_summary") or "").strip(),
        }
        suggestions.append(LccSuggestion(
            book_id=book_id,
            title=book.title,
            authors=book.authors,
            current=current_map.get(book_id, {}),
            proposed=proposed,
            confidence=item.get("confidence", "low"),
            source=item.get("source", "").strip(),
            notes=item.get("notes", "").strip(),
        ))
    return suggestions


# ── Comments prompt + parsing ─────────────────────────────────────────────────

_COMMENTS_SECTION_KEYS = [
    ("the_book",                     "The Book"),
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
  "the_book": "<plain prose — no HTML tags>",
  "something_you_might_not_know": "<plain prose, or empty string if nothing noteworthy>",
  "why_read_it": "<plain prose — no HTML tags>",
  "confidence": "high" | "medium" | "low",
  "notes": "<one short sentence — main caveat or key evidence>"
}

Return ONLY the JSON array. No markdown fences, no commentary outside the array.
"""


def _build_comments_system_prompt(tone_override: str | None = None) -> str:
    reader_profile = _load_rules("reader_profile.md")
    comments_rules = _load_rules("comments.md")

    preamble = _COMMENTS_PROMPT_PREAMBLE
    if tone_override:
        preamble += f"\n\n### TONE OVERRIDE FOR THIS CALL\n{tone_override}\n"

    return (
        preamble
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


def _format_comments_html(sections: dict[str, str]) -> str:
    parts = []
    for key, label in _COMMENTS_SECTION_KEYS:
        text = (sections.get(key) or "").strip()
        if not text:
            continue
        parts.append(f"<h3>{label}</h3>\n<p>{text}</p>")
    return "\n".join(parts)


def _parse_comments_response(raw: str, books: list[Book]) -> list[CommentsSuggestion]:
    items = _extract_json_array(raw)
    book_map = {b.id: b for b in books}
    suggestions: list[CommentsSuggestion] = []
    for item in items:
        book_id = item.get("id")
        book = book_map.get(book_id)
        if book is None:
            continue
        sections = {
            key: (item.get(key) or "").strip()
            for key, _ in _COMMENTS_SECTION_KEYS
        }
        suggestions.append(CommentsSuggestion(
            book_id=book_id,
            title=book.title,
            authors=book.authors,
            sections=sections,
            html=_format_comments_html(sections),
            confidence=item.get("confidence", "low"),
            notes=item.get("notes", "").strip(),
        ))
    return suggestions


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


def _parse_tag_cleanup_response(
    raw: str,
    counts: dict[str, int],
) -> list[TagOperation]:
    items = _extract_json_array(raw)
    ops: list[TagOperation] = []
    for item in items:
        sources = [t.strip() for t in (item.get("source_tags") or []) if t.strip()]
        targets = [t.strip() for t in (item.get("target_tags") or []) if t.strip()]
        reason = (item.get("reason") or "").strip()
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


def _parse_tags_review_response(
    raw: str,
    book: Book,
    current_tags: list[str],
) -> TagsReviewSuggestion:
    try:
        item = _extract_json_object(raw)
    except RuntimeError as e:
        return TagsReviewSuggestion(
            book_id=book.id, title=book.title, authors=book.authors,
            current_tags=current_tags, proposed_tags=list(current_tags),
            assessment="complete", confidence="low",
            parse_error=str(e),
        )
    proposed = [
        t.strip() for t in (item.get("proposed_tags") or [])
        if isinstance(t, str) and t.strip()
    ]
    if not proposed:
        proposed = list(current_tags)
    return TagsReviewSuggestion(
        book_id=book.id,
        title=book.title,
        authors=book.authors,
        current_tags=list(current_tags),
        proposed_tags=proposed,
        assessment=item.get("assessment", "complete"),
        confidence=item.get("confidence", "medium"),
        notes=(item.get("notes") or "").strip(),
    )


def _parse_tags_response(
    raw: str,
    books: list[Book],
    tags_map: dict[int, list[str]],
) -> list[TagsSuggestion]:
    items = _extract_json_array(raw)
    book_map = {b.id: b for b in books}
    suggestions: list[TagsSuggestion] = []
    for item in items:
        book_id = item.get("id")
        book = book_map.get(book_id)
        if book is None:
            continue
        raw_tags = item.get("tags") or []
        proposed = [t.strip() for t in raw_tags if isinstance(t, str) and t.strip()]
        suggestions.append(TagsSuggestion(
            book_id=book_id,
            title=book.title,
            authors=book.authors,
            current_tags=tags_map.get(book_id, []),
            proposed_tags=proposed,
            confidence=item.get("confidence", "low"),
            notes=item.get("notes", "").strip(),
        ))
    return suggestions
