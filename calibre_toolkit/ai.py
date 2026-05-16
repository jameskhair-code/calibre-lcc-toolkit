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


@dataclass
class LccSuggestion:
    book_id: int
    title: str
    authors: list[str]
    current: dict[str, str]            # current values for the four LCC fields
    proposed: dict[str, str]           # AI-proposed values for the four LCC fields
    confidence: Literal["high", "medium", "low"]
    source: str = ""
    notes: str = ""
    parse_error: str = ""              # populated if AI output failed validation

    @property
    def authors_display(self) -> str:
        return " & ".join(self.authors)

    @property
    def any_change(self) -> bool:
        return any(
            self.proposed.get(k, "") != self.current.get(k, "")
            for k in ("lcc", "lcc_primary_class", "lcc_secondary_class", "lcc_class_path")
        )


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

        # What the AI returned (before code normalization)
        raw_title = item.get("title", book.title).strip()
        # AI sometimes collapses multiple authors into one semicolon-separated string
        raw_authors = []
        for a in item.get("authors", book.authors):
            if ";" in a:
                raw_authors.extend(x.strip() for x in a.split(";") if x.strip())
            else:
                raw_authors.append(a.strip())

        # Apply code normalization (diacritics, dashes) on top of AI suggestion
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
                # AI left it alone; code normalization made the change
                parts = []
                if code_changed_title:
                    parts.append("title")
                if code_changed_authors:
                    parts.append("authors")
                notes = f"Americanized special characters in {' and '.join(parts)} (diacritics and dashes converted to plain ASCII)."
            else:
                # AI made changes but wrote "no changes needed" — generate a clean fallback
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

    def suggest_lcc(
        self,
        books: list[Book],
        current_map: dict[int, dict[str, str]],
        batch_size: int = 10,
    ) -> list["LccSuggestion"]:
        """Process books in batches and return LCC suggestions.

        current_map[book_id] = dict of current values for the four LCC fields
        (used to give the model context about what's already there).
        """
        results: list[LccSuggestion] = []
        batches = [books[i:i + batch_size] for i in range(0, len(books), batch_size)]
        for batch in batches:
            results.extend(self._process_lcc_batch(batch, current_map))
        return results

    def _process_lcc_batch(
        self,
        books: list[Book],
        current_map: dict[int, dict[str, str]],
    ) -> list["LccSuggestion"]:
        system_prompt = _build_lcc_system_prompt()
        user_msg = _build_lcc_user_message(books, current_map)
        if self.provider == "openai":
            raw = self._call_openai(user_msg, system_prompt)
        else:
            raw = self._call_anthropic(user_msg, system_prompt)
        return _parse_lcc_response(raw, books, current_map)

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
  "lcc_class_path": "<subject descriptor per PATH section — 3–5 noun phrases separated by ·>",
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
        if any(current.get(k) for k in ("lcc", "lcc_primary_class", "lcc_secondary_class", "lcc_class_path")):
            item["current"] = {k: current.get(k, "") for k in
                               ("lcc", "lcc_primary_class", "lcc_secondary_class", "lcc_class_path")}
        payload.append(item)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _parse_lcc_response(
    raw: str,
    books: list[Book],
    current_map: dict[int, dict[str, str]],
) -> list[LccSuggestion]:
    # Strip optional markdown fences in case the model ignores instructions
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        items = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"AI returned invalid JSON: {e}\n\nRaw response:\n{raw[:500]}")

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
            "lcc_class_path": (item.get("lcc_class_path") or "").strip(),
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
