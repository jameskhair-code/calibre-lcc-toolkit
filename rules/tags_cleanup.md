# Tag Cleanup Rules — AI Semantic Pass
# Literary Awards & Nominees Collection — MQG-05
#
# A deterministic scanner has ALREADY handled obvious patterns before this prompt
# runs. Your job: handle the SEMANTIC cases the scanner cannot — variant spellings,
# near-synonyms, plural/singular collapses, and any remaining noise tags.
# See SECTION SCANNER below for the full list of what the scanner already does.


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
## SECTION REFUSAL — When Not to Act
---

REFUSAL-01: When you are not confident a merge is semantically correct,
             do NOT propose it. Tags are easier to add later than to
             reconstruct across thousands of books after a bulk drop.

REFUSAL-02: If a tag is niche, unusual, or unfamiliar to you, leave it
             alone. Niche tags (e.g. "Solarpunk", "Hopepunk", "Noblebright",
             "Cli-fi") are legitimate subject tags that carry real search
             value. Your uncertainty is not evidence the tag is wrong.

REFUSAL-03: If you cannot state a reason in ≤10 words that would be
             obviously correct to a librarian, do not propose the operation.

REFUSAL-04: The TRIAGE rule (GEN-01c) applies always: when uncertain,
             skip. A missed normalization is a minor search annoyance.
             A wrong merge is irreversible data loss without a full
             re-enrichment pass.


---
## SECTION SCANNER — What the Scanner Already Handles
---

Do NOT propose operations for anything in this list. The scanner has
already handled these before your prompt runs. Proposing them again would
be a no-op at best and confusing at worst.

The scanner handles:
  • Whitespace and case normalization (leading/trailing spaces, encoding artifacts)
  • BISAC classification codes (e.g. "HIS036140 HISTORY / Military / General")
  • Calibre slash-taxonomy noise: "Fiction / Historical" → "Historical Fiction",
    "Fiction / Science Fiction / General" → "Science Fiction", etc.
  • Known plural/abbreviation variants in the Calibre taxonomy:
    "Sci-Fi", "SF", "scifi" → "Science Fiction"
    "Non-Fiction", "non fiction" → "Nonfiction"
    "Novels" → "Novel", "Memoirs" → "Memoir", "Plays" → "Drama"
    "WWII" → "World War II", "WWI" → "World War I"
    "Post Apocalyptic" → "Post-Apocalyptic"
    "Coming of Age" → "Coming-of-Age Fiction"
    "Magic Realism" → "Magical Realism"
    "Alternative History" → "Alternate History"
  • Bare date-range → period name conversions (already done):
    1939-1945 → World War II      1914-1918 → World War I
    1861-1865 → American Civil War  1775-1783 → American Revolution
    1865-1877 → Reconstruction    1837-1901 → Victorian Era
    1918-1939 → Interwar Period   1945-1991 → Cold War
    1789-1799 → French Revolution  1936-1939 → Spanish Civil War
    1955-1975 → Vietnam War       1950-1953 → Korean War
    1929-1939 → Great Depression  1607-1776 → Colonial America
  • LCSH heading chains (e.g. "United States -- History -- 20th century")
  • LCSH person-date headings (e.g. "Hemingway, Ernest, 1899-1961")
  • Goodreads reading-state tags ("to-read", "currently-reading", "dnf")
  • Unbalanced parentheses, control characters, URL-like strings
  • Tags over ~60 characters (likely LCSH full headings)

What the scanner does NOT handle (your job):
  • True spelling variants not in the taxonomy ("Fant'sy" is unlikely but
    "British Literature" vs. "English Literature" is a semantic question)
  • Near-synonym merges ("Espionage" vs. "Spy Thriller" — semantic, not mechanical)
  • Genuinely ambiguous form collapses ("Short Story" → "Short Stories")
  • Any merge that requires understanding what the book is about


---
## SECTION GEN — Output Format
---

GEN-01: Return a JSON array. Each element is one operation:
         {
           "source_tags": ["<tag>", ...],
           "target_tags": ["<tag>", ...],
           "reason": "<≤10 words>"
         }

GEN-01b: KEEP REASONS SHORT. Maximum 10 words — enforced programmatically;
          excess words are truncated automatically. No rule numbers.
          Good:  "Plural variant"
          Good:  "Calibre slash-taxonomy noise"
          Bad:   "Per MERGE-02, compound '&' form tag collapses to the most
                  common single form as the book is most likely a biography…"

GEN-01c: TRIAGE. The tag list may be very long. Only propose operations
          for CLEAR cases. Skip uncertain or borderline tags entirely —
          a missed operation is far better than a wrong one.

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


---
## SECTION EXAMPLES — Reference Input/Output Pairs
---

EXAMPLE-01: Variant spelling merge (propose this)

  Library contains: "Sci-Fi" (42 books), "Sci Fi" (7 books), "SF" (3 books),
                    "Science Fiction" (210 books)

  Correct operation:
    {
      "source_tags": ["Sci-Fi", "Sci Fi", "SF"],
      "target_tags": ["Science Fiction"],
      "reason": "Spelling variants of existing canonical tag"
    }

  Why: All three source tags mean exactly "Science Fiction". Any book correctly
  tagged with "Sci-Fi" is correctly tagged "Science Fiction". The merge is safe.

EXAMPLE-02: Niche tag — do NOT touch

  Library contains: "Solarpunk" (12 books), "Hopepunk" (4 books),
                    "Cli-fi" (8 books)

  Correct operation: (none — omit these entirely)

  Why: These are legitimate science fiction sub-genres with active communities.
  "Solarpunk" is NOT a variant of "Science Fiction" — it is a specific aesthetic
  and political tradition. Merging would destroy real search value. When in doubt
  about a sub-genre, see REFUSAL-02.

EXAMPLE-03: Drop a reading-state tag

  Library contains: "to-read" (15 books), "currently-reading" (3 books)

  Correct operation:
    { "source_tags": ["to-read"], "target_tags": [], "reason": "Goodreads reading-state tag" },
    { "source_tags": ["currently-reading"], "target_tags": [], "reason": "Goodreads reading-state tag" }

  Why: These are personal shelf annotations, not subject tags. They carry no
  search value and pollute the tag vocabulary. DROP is correct.
