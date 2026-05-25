
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

Confidence semantics — see rules/confidence.md for the canonical tier
definitions, then SECTION CONF in the comments rules for per-section
evidence calibration.

Return ONLY the JSON array. No markdown fences, no commentary outside the array.
