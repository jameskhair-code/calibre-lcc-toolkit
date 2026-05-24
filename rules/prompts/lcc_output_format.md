
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

Confidence semantics — see rules/confidence.md for the canonical tier
definitions, then SECTION CONF in this file for LCC-specific calibration.

source_authority semantics — see SRC-06 in the rules:
  - "lc_catalog"         only if you can cite a specific LC record (LCCN or ISBN).
  - "worldcat_consensus" only if you can cite multiple library catalog records.
  - "open_library"       only if you can cite an OL bibkey/work.
  - "ai_inference"       otherwise — including all reasoning from training data,
                         topic inference, or schedule-derived classification.

You are being called as a fallback for books that already failed direct catalog
lookups. Return "ai_inference" unless you can cite a specific catalog record.

Return ONLY the JSON array. No markdown fences, no commentary outside the array.
