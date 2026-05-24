
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

Confidence semantics — see rules/confidence.md for the canonical tier
definitions, then SECTION CONF in the tags rules for tag-specific calibration.

Return ONLY the JSON array. No markdown fences, no commentary outside the array.
