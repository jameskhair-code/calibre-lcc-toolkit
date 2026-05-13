"""
AI provider abstraction. Supports OpenAI (default) and Anthropic (Claude).
Books are sent in batches to minimise API calls and cost.
"""

from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .db import Book

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
  "notes": "<one sentence: what changed and why, or 'No changes needed'>"
}
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
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"AI returned invalid JSON: {e}\n\nRaw response:\n{raw[:500]}")

    book_map = {b.id: b for b in books}
    suggestions = []
    for item in items:
        book_id = item["id"]
        book = book_map.get(book_id)
        if book is None:
            continue
        suggested_title = item.get("title", book.title).strip()
        suggested_authors = [a.strip() for a in item.get("authors", book.authors)]
        title_changed = suggested_title != book.title
        authors_changed = suggested_authors != book.authors

        notes = item.get("notes", "")
        # If the AI says "no changes needed" but actually made changes, override the note
        if (title_changed or authors_changed) and notes.lower().strip(".").strip() == "no changes needed":
            parts = []
            if title_changed:
                parts.append("Title updated")
            if authors_changed:
                parts.append("Authors updated")
            notes = "; ".join(parts) + " (AI note overridden — was incorrect)"

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


class AIClient:
    def __init__(self, provider: str, api_key: str, model: str | None = None):
        self.provider = provider.lower()
        self.api_key = api_key
        if self.provider == "openai":
            self.model = model or "gpt-4o-mini"
        elif self.provider == "anthropic":
            self.model = model or "claude-sonnet-4-6"
        else:
            raise ValueError(f"Unknown provider '{provider}'. Use 'openai' or 'anthropic'.")

    def suggest_cleanup(self, books: list[Book], batch_size: int = 50) -> list[CleanupSuggestion]:
        """Process books in batches and return all suggestions."""
        results: list[CleanupSuggestion] = []
        batches = [books[i:i + batch_size] for i in range(0, len(books), batch_size)]
        for batch in batches:
            results.extend(self._process_batch(batch))
        return results

    def _process_batch(self, books: list[Book], rules_file: str = "author_title.md") -> list[CleanupSuggestion]:
        user_msg = _build_user_message(books)
        system_prompt = _build_system_prompt(rules_file)
        if self.provider == "openai":
            raw = self._call_openai(user_msg, system_prompt)
        else:
            raw = self._call_anthropic(user_msg, system_prompt)
        return _parse_response(raw, books)

    def _call_openai(self, user_msg: str, system_prompt: str) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()

    def _call_anthropic(self, user_msg: str, system_prompt: str) -> str:
        from anthropic import Anthropic
        client = Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        return response.content[0].text.strip()
