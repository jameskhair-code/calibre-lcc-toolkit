"""
AI provider abstraction. Supports OpenAI (default) and Anthropic (Claude).
Books are sent in batches to minimise API calls and cost.
"""

from __future__ import annotations
import json
import textwrap
from dataclasses import dataclass
from typing import Literal

from .db import Book


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


SYSTEM_PROMPT = textwrap.dedent("""
    You are a metadata librarian specialising in literary fiction and award-winning books.
    Your job is to clean book titles and author names for a Calibre library called
    "Collection – Literary Awards and Nominees".

    Rules you MUST follow:
    1. TITLES
       - Use title case (every major word capitalised).
       - Remove edition markers like "(Revised Edition)", "(2nd ed.)", "Revised and Updated", etc.
         UNLESS the edition is integral to the title (e.g. "The Annotated Waste Land").
       - Remove award parentheticals like "(Booker Prize Winner)", "(National Book Award)",
         "[Man Booker Prize]", etc.
       - Preserve legitimate subtitles after a colon or em-dash UNLESS the subtitle is generic
         (e.g. "A Novel", "A Memoir", "Stories"). Remove generic subtitles.
       - Do NOT change the spelling of proper nouns, invented words, or foreign-language titles.
       - If the title looks correct already, return it unchanged.

    2. AUTHORS
       - Format: "First Last" (not "Last, First").
       - Multiple authors separated by " & ".
       - Remove trailing roles like "(editor)", "(ed.)", "(translator)", "(trans.)",
         "(illustrator)", etc. — but keep the person's name.
       - Normalise diacritics only if the form without is clearly an error
         (e.g. "Marquez" → "García Márquez" if you are confident; otherwise leave unchanged).
       - Corporate/institution authors: leave as-is.
       - If the author looks correct already, return it unchanged.

    3. CONFIDENCE
       - "high"   → change is clearly correct, mechanical rule applied
       - "medium" → change is probably right but involves a judgment call
       - "low"    → you are unsure; flag for human review

    4. OUTPUT FORMAT
       Respond with a JSON array, one object per book, in the SAME ORDER as the input.
       Each object must have exactly these keys:
       {
         "id": <integer>,
         "title": "<cleaned title>",
         "authors": ["<First Last>", ...],
         "confidence": "high" | "medium" | "low",
         "notes": "<brief explanation of changes, or 'No changes needed'>"
       }
       Return ONLY the JSON array. No markdown fences, no explanation outside the array.
""").strip()


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
        suggestions.append(CleanupSuggestion(
            book_id=book_id,
            original_title=book.title,
            original_authors=book.authors,
            suggested_title=suggested_title,
            suggested_authors=suggested_authors,
            confidence=item.get("confidence", "medium"),
            title_changed=suggested_title != book.title,
            authors_changed=suggested_authors != book.authors,
            notes=item.get("notes", ""),
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

    def _process_batch(self, books: list[Book]) -> list[CleanupSuggestion]:
        user_msg = _build_user_message(books)
        if self.provider == "openai":
            raw = self._call_openai(user_msg)
        else:
            raw = self._call_anthropic(user_msg)
        return _parse_response(raw, books)

    def _call_openai(self, user_msg: str) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()

    def _call_anthropic(self, user_msg: str) -> str:
        from anthropic import Anthropic
        client = Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return response.content[0].text.strip()
