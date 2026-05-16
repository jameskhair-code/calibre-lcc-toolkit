# Tag Cleanup Rules — AI Semantic Pass
# Literary Awards & Nominees Collection — MQG-05
#
# A deterministic scanner has ALREADY handled obvious patterns before this prompt
# runs: bare date ranges, LCSH date+name subject headings, Calibre taxonomy noise
# ("Fiction / Historical" → "Historical Fiction"), simple case normalization,
# and known period-name lookups (1939-1945 → World War II).
#
# Your job: handle the SEMANTIC cases the scanner cannot — variant spellings,
# near-synonyms, plural/singular collapses, and any remaining noise tags.


---
## SECTION PRINCIPLE — Normalize, Don't Generalize
---

PRIN-01: The goal is to merge variant spellings and obvious duplicates of the
          SAME concept into one canonical form. It is NOT to collapse specific
          tags into broader parents.

PRIN-02: When in doubt, do NOT merge. A missed merge causes a minor search
          inconsistency. A wrong merge causes data loss that cannot be undone
          without re-enriching all affected books.

PRIN-03: Two tags should only be merged when any book correctly tagged with
          one would also be correctly tagged with the other.

PRIN-04: Do NOT invent new vocabulary in target_tags. Every target tag must
          either already exist in the library OR be a standard controlled-
          vocabulary Form tag (see FORM section).


---
## SECTION MERGE — What to Merge
---

MERGE-01: MERGE these variant types:
            - Spelling variants
            - Case variants (when otherwise identical)
            - Plural/singular when meaning is identical: "Novels" → "Novel"
            - Punctuation variants the scanner missed
            - Abbreviations: "WWII" → "World War II" (scanner usually catches this)
            - Redundant qualifiers: "History - General History" → "History"

MERGE-02: For tags that join two controlled Form tags compounded with "&" or "/",
          collapse into the most likely single Form unless the book is clearly
          the other ("Biography & Autobiography" → "Biography", since Autobiography
          has its own controlled tag).


---
## SECTION DROP — What to Drop
---

DROP-01: DROP a tag entirely (target_tags = []) when it has no search value
          and no clean canonical equivalent.

DROP-02: Tags suitable for DROP include:
           - Goodreads shelves / reading-state tags: "to-read", "currently-reading"
           - Tags that are personal annotations rather than subjects
           - Hyper-specific single-book tags with no broader meaning
           - Compound tags where no clean component can be salvaged

DROP-03: Be conservative with DROP. If a tag is unusual but might be a real
          subject, leave it alone (no operation). Subsequent enrichment passes
          handle per-book tag quality.


---
## SECTION SKIP — What NOT to Touch
---

SKIP-01: Do NOT merge sub-genres into parent genres. Sub-genres carry
          distinct search value and MUST be preserved:
           Space Opera ≠ Science Fiction
           Hard Science Fiction ≠ Science Fiction
           Military Science Fiction ≠ Science Fiction
           Cyberpunk ≠ Science Fiction
           Epic Fantasy ≠ Fantasy
           Urban Fantasy ≠ Fantasy
           Dark Fantasy ≠ Fantasy
           Psychological Thriller ≠ Thriller
           Legal Thriller ≠ Thriller
           Southern Gothic ≠ Gothic
           Magic Realism ≠ Fantasy
           Dystopian Fiction ≠ Science Fiction

SKIP-02: Do NOT merge Speculative Fiction into Fantasy or Science Fiction.
          It is a broader umbrella; it stays distinct.

SKIP-03: Do NOT merge geographically specific tags into generic ones:
           "Colonial America" ≠ "American Revolution"
           Geographic literary tags often add real specificity

SKIP-04: Do NOT merge distinct literary forms:
           Anthologies (multi-author) ≠ Essay Collection (single-author)
           Memoir ≠ Biography ≠ Autobiography
           True Crime ≠ Crime (form ≠ subject)

SKIP-05: Do NOT merge genuinely distinct concepts:
           Imperialism ≠ Colonialism
           Political History ≠ Political Science
           Philosophical Fiction ≠ Philosophy
           Indigenous ≠ Native American
           Abolitionism ≠ Slavery
           Economic History ≠ Economics

SKIP-06: Do NOT merge humor sub-types: Dark Humor, Black Humor, Dark Comedy
          carry meaningful distinction from generic "Humor".

SKIP-07: Do NOT merge tags at different specificity scopes: "Family" ≠
          "Family Drama" ≠ "Family Saga".


---
## SECTION FORM — Controlled Form Vocabulary
---

FORM-01: For Form tags specifically, the controlled list is:
           Novel, Short Stories, Poetry, Drama, Memoir, Autobiography,
           Biography, History, Nonfiction, Essay Collection, Literary
           Criticism, Philosophy, Science, Political Science, Journalism

FORM-02: Do NOT merge "Anthologies" or "Collections" into "Essay Collection" —
          multi-author anthologies are a different form.


---
## SECTION GEN — Output Format
---

GEN-01: Return a JSON array. Each element is one operation:
         {
           "source_tags": ["<tag>", ...],
           "target_tags": ["<tag>", ...],
           "reason": "<one short sentence>"
         }

GEN-02: Operation semantics:
         - MERGE:  source_tags = [A, B, C], target_tags = [X]   → rename A,B,C to X
         - RENAME: source_tags = [A],       target_tags = [X]   → rename A to X
         - DROP:   source_tags = [A, ...],  target_tags = []    → remove A from all books

GEN-03: Do NOT produce SPLIT operations (single source → multiple targets).
         Those are handled either by the scanner or by per-book enrichment.

GEN-04: target_tags must contain only tags that already exist in the library
         or are standard controlled-vocabulary Form tags. Do not invent.

GEN-05: If no operations are warranted, return [].

GEN-06: No markdown fences. No commentary outside the JSON array.
