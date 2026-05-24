
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

Confidence semantics — see rules/confidence.md for the canonical tier
definitions ("high" auto-applies; "medium" is reviewed; "low" is skipped).

Notes guidance:
- If you made changes: describe specifically what you changed and which rule applies.
  Good: "Removed generic subtitle per T-SUB-02."
  Good: "Lowercased preposition 'with' per title case rules."
  Good: "Removed series parenthetical '(The Way Book 1)' per T-SER-02."
- If you made NO changes: write "Already correctly formatted."
- NEVER write "No changes needed" if you actually changed the title or authors.
- Keep notes to one clear sentence.

Return ONLY the JSON array. No markdown fences, no explanation outside the array.
