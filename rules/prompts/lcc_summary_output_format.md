
---
## OUTPUT FORMAT

Respond with a JSON array, one object per book, in the SAME ORDER as
the input. Each object must have exactly these keys:
{
  "id": <integer>,
  "lcc_summary": "<one-sentence subject summary per SUMMARY rules, 20–40 words; empty string if identity mismatch>"
}

Return ONLY the JSON array. No markdown fences, no commentary outside the array.
