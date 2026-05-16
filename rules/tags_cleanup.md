# Tag Cleanup Rules
# Literary Awards & Nominees Collection — MQG-05
#
# Rules for normalising the existing tag vocabulary across the whole library.
# Goal: fix formatting/spelling inconsistencies. Do NOT generalize or flatten.


---
## SECTION PRINCIPLE — Normalize, Don't Generalize
---

PRIN-01: The purpose of cleanup is to merge variant spellings and obvious
          duplicates of the SAME concept into one canonical form.
          It is NOT to collapse specific tags into broader parents.

PRIN-02: When in doubt, do NOT merge. A missed merge causes a search
          inconsistency. A wrong merge causes data loss and cannot be undone
          without re-enriching all affected books.

PRIN-03: Only propose a merge when the tags are genuinely interchangeable —
          i.e., any book correctly tagged with one would also be correctly
          tagged with the other.


---
## SECTION MERGE — What to Merge
---

MERGE-01: MERGE these variant types:
            - Spelling variants: "Scifi" → "Science Fiction"
            - Case variants: "coming of age" → "Coming-of-Age Fiction"
            - Hyphenation/spacing variants: "Post Apocalyptic" →
              "Post-Apocalyptic" (per formatting rules)
            - Abbreviations: "WWII" → "World War II", "WWI" → "World War I"
            - Plural/singular when meaning is identical: "Novels" → "Novel"
            - Calibre taxonomy noise (slash-separated, colon-separated, or
              parenthetical forms): "Fiction / Historical" → "Historical
              Fiction", "Fiction: Science Fiction - General" → "Science Fiction"
            - Redundant qualifiers that add nothing: "Fiction - General"
              → "Novel", "History - General History" → "History"

MERGE-02: MERGE compound tags that redundantly join two controlled-vocabulary
          Form tags when one already exists: "Biography & Autobiography" →
          "Biography" (Autobiography is a separate controlled tag; the compound
          collapses into the more common form unless the book is clearly
          autobiography).


---
## SECTION SKIP — What NOT to Merge
---

SKIP-01: Do NOT merge sub-genres into parent genres.
          Sub-genres carry distinct search value and must be preserved.
           Space Opera ≠ Science Fiction (keep both; do not merge Space Opera
             into Science Fiction)
           Hard Science Fiction ≠ Science Fiction
           Military Science Fiction ≠ Science Fiction
           Cyberpunk ≠ Science Fiction
           Epic Fantasy ≠ Fantasy
           Urban Fantasy ≠ Fantasy
           Dark Fantasy ≠ Fantasy
           Psychological Thriller ≠ Thriller
           Legal Thriller ≠ Thriller
           Southern Gothic ≠ Gothic (Southern Gothic is a distinct American
             literary tradition)
           Magic Realism ≠ Fantasy
           Dystopian Fiction ≠ Science Fiction

SKIP-02: Do NOT merge Speculative Fiction into Fantasy or Science Fiction.
          "Speculative Fiction" is a broader umbrella category that explicitly
          encompasses both and is used when the genre split is unclear.
          It should remain as its own tag.

SKIP-03: Do NOT merge geographically specific tags into generic ones when
          the geography is meaningful.
           "American Historical Fiction" may be a valid distinct tag
           "Colonial America" ≠ "American Revolution" (different periods)
           "United States History" — consider whether it overlaps with
             the general "History" tag or adds specificity

SKIP-04: Do NOT merge different literary forms into each other.
           Anthologies (multi-author) ≠ Essay Collection (single-author)
           Memoir ≠ Biography ≠ Autobiography (each is a distinct controlled
             Form tag)
           True Crime ≠ Crime (True Crime is a genre/form; Crime is a subject)

SKIP-05: Do NOT merge concepts that are genuinely distinct even if related.
           Imperialism ≠ Colonialism (Imperialism is broader, includes
             economic/informal empire)
           Political History ≠ Political Science (one is historical subject,
             one is academic discipline / Form)
           Philosophical Fiction ≠ Philosophy (subject tag ≠ Form tag)
           Indigenous ≠ Native American (Indigenous is global; Native American
             is specifically North American)
           Abolitionism ≠ Slavery (the movement to end it ≠ the institution)
           Economic History ≠ Economics (historical approach ≠ discipline)
           True Crime ≠ Crime (genre ≠ subject)

SKIP-06: Do NOT merge humor sub-types that carry meaningful distinction.
           Dark Humor / Black Humor / Dark Comedy are specific enough to keep
           as distinct tags alongside a general "Humor" tag.

SKIP-07: Do NOT merge tags that are the same word but used at different
          scopes — e.g., "Family" (broad subject) should not absorb
          "Family Drama" or "Family Saga" (specific sub-types).


---
## SECTION FORM — Controlled Form Vocabulary
---

FORM-01: For Form tags specifically, the controlled list is:
           Novel, Short Stories, Poetry, Drama, Memoir, Autobiography,
           Biography, History, Nonfiction, Essay Collection, Literary
           Criticism, Philosophy, Science, Political Science, Journalism

FORM-02: Variants that are clearly the same Form tag should merge into
          the canonical string. For example:
           "Non-Fiction" → "Nonfiction"
           "Non Fiction" → "Nonfiction"
           "Novels" → "Novel"
           "Short Story Collection" → "Short Stories"
           "Plays" → "Drama"
           "Theatre" → "Drama"
           "Theater" → "Drama"
           "Personal Memoirs" → "Memoir"
           "Biographies" → "Biography"
           "Essays" → "Essay Collection" (ONLY when clearly single-author essays)
           "Investigative Journalism" → "Journalism"
           "Reportage" → "Journalism"

FORM-03: Do NOT merge "Anthologies" or "Collections" into "Essay Collection".
          Multi-author anthologies and collections are a different form.
          Leave them as-is or flag separately.


---
## SECTION GEN — Output Format
---

GEN-01: Return a JSON array. Each element proposes one merge group:
         {
           "canonical": "<exact string — Title Case, ≤4 words>",
           "merge_from": ["<tag to rename>", ...],
           "reason": "<one short sentence>"
         }

GEN-02: "canonical" is the tag to KEEP. Every tag in "merge_from" will be
         renamed to "canonical" across all books that carry it.

GEN-03: Do NOT include the canonical tag itself in "merge_from".

GEN-04: If a proposed merge would violate any SKIP rule, omit it entirely.

GEN-05: Return [] if no merges are warranted.

GEN-06: No markdown fences. No commentary outside the JSON array.
