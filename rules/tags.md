# Tag Enrichment Rules
# Literary Awards & Nominees Collection — MQG-05
#
# Rules for reviewing and enriching subject tags per book.
# Existing accurate tags are kept (and normalized). Noise is removed.
# Missing coverage is added. Rules are grouped by category and numbered.


---
## SECTION SCOPE — What This Task Is
---

SCOPE-01: For each book, review the existing tags and produce a final
           enriched set of 4–8 tags drawn from four category types:
           Form, Subject, Period, and Geography. Not every category
           must be represented — use only what is genuinely applicable.

SCOPE-02: Tags are the primary search surface for this library. A reader
           searching for "Cold War" or "Space Opera" expects to find all
           relevant books. Accuracy and specificity matter more than
           broad coverage.

SCOPE-03: Source material in priority order:
             1. lcc_secondary_class — the most reliable subject signal
             2. lcc_summary — the specific argument and subject
             3. lcc_primary_class — broad class fallback
             4. existing current_tags — review and reuse accurate ones
             5. Title and authors — use when LCC data is absent

SCOPE-04: Do not repeat the LCC hierarchy verbatim as tags. Translate it
           into readable, searchable strings.

SCOPE-05: Do not add award names as tags. Award data lives in other fields.

SCOPE-06: Do not add the author's name or nationality as a tag.


---
## SECTION EXISTING — Handling Books That Already Have Tags
---

EXISTING-01: When a book has current_tags, evaluate each existing tag
              individually. Do not discard the existing set wholesale.

EXISTING-02: KEEP an existing tag if:
               - It accurately describes the book's content
               - It is ≤4 words, Title Case, no commas
               - It has genuine search value (someone would search for it)
              Normalize its form if needed (capitalization, hyphenation)
              but keep its meaning intact.

EXISTING-03: DROP an existing tag if:
               - It is pure noise: "Fiction", "Literary", "World Literature",
                 "Own Voices", "General", "Sagas"
               - It is a Goodreads shelf or reading-state tag
               - It is a Calibre taxonomy artifact (e.g. "Fiction / Historical",
                 "Fiction: Science Fiction - General")
               - It duplicates another tag at a less specific level when
                 the more specific tag is also present
               - It is so broad it adds no discriminating value: a book
                 tagged "Novel" and "Historical Fiction" does not also need
                 "Fiction"

EXISTING-04: ADD tags to fill genuine gaps in coverage:
               - Every book must have exactly one Form tag
               - Add Subject tags if the existing set lacks meaningful subject
                 coverage (not just form and period)
               - Add Period or Geography only when genuinely applicable

EXISTING-05: If the existing tags already provide good 4–8 coverage after
              KEEP/DROP, additional tags are not required. Quality over quantity.


---
## SECTION FORM — Category 1: Form / Genre
---

FORM-01: Every book gets exactly one Form tag. Pick the best fit from
          the controlled list below. Use the string exactly as written.

FORM-02: Controlled Form vocabulary (use EXACTLY as written):
           Novel
           Short Stories
           Poetry
           Drama
           Memoir
           Autobiography
           Biography
           History
           Nonfiction
           Essay Collection
           Literary Criticism
           Philosophy
           Science
           Political Science
           Journalism

FORM-03: Guidance for ambiguous cases:
           - A book-length argument about ideas → Philosophy or Political Science
             depending on primary subject; Nonfiction is the fallback
           - A life story told by the subject → Memoir (personal, selective)
             vs. Autobiography (more comprehensive, chronological)
           - A life story told by someone else → Biography
           - Reported narrative about real events → Journalism if primarily
             investigative/reported; History if the framing is scholarly
             or the events are at significant historical remove
           - A collection of pieces by one author → Essay Collection
           - Literary analysis or criticism of other works → Literary Criticism

FORM-04: Do NOT use multiple Form tags. One per book.


---
## SECTION SUBJECT — Category 2: Subject
---

SUBJECT-01: 1–4 subject tags describing what the book is specifically about.
             Derive from lcc_secondary_class, lcc_summary, and existing tags.

SUBJECT-02: Subject tags are Title Case noun phrases. No articles at the
             start. No verbs.
              Good: "Military History", "Cold War", "Public Health",
                    "Space Opera", "Hard Science Fiction", "Cyberpunk"
              Bad:  "About the Cold War", "examining military history"

SUBJECT-03: Be specific. Prefer specific sub-genre or sub-subject tags
             over broad parent categories. This library values depth —
             a reader searching for "Space Opera" wants space opera books,
             not all science fiction.
              Too broad:  "Science Fiction" alone (when more specific applies)
              Right:      "Science Fiction" + "Space Opera" (both are useful)
              Right:      "Science Fiction" + "Hard Science Fiction"
              Right:      "Fantasy" + "Epic Fantasy"
              Right:      "Thriller" + "Psychological Thriller"

SUBJECT-04: Sub-genre tags DO NOT replace the parent — they ADD to it.
             A space opera is both "Science Fiction" AND "Space Opera".
             An epic fantasy is both "Fantasy" AND "Epic Fantasy".
             A psychological thriller is both "Thriller" AND "Psychological
             Thriller". Both tags are kept.

SUBJECT-05: Valid sub-genre tags include but are not limited to:
             Science Fiction sub-genres: Space Opera, Hard Science Fiction,
               Cyberpunk, Military Science Fiction, Biopunk, Solarpunk,
               First Contact, Generation Ship, Time Travel
             Fantasy sub-genres: Epic Fantasy, High Fantasy, Urban Fantasy,
               Dark Fantasy, Sword & Sorcery, Portal Fantasy, Grimdark
             Thriller sub-genres: Psychological Thriller, Legal Thriller,
               Political Thriller, Spy Thriller, Medical Thriller
             Literary traditions: Southern Gothic, Gothic Fiction,
               Magic Realism, Postcolonial Fiction, Afrofuturism,
               New Weird, Stream of Consciousness

SUBJECT-06: Do not duplicate the Form tag as a subject tag.
              Bad:  Form="Biography", Subject="Biography"
              Good: Form="Biography", Subject="Political Biography" or
                    the relevant subject field alone

SUBJECT-07: For literature (novels, poetry, short stories), subject tags
             describe the work's themes or the tradition it belongs to,
             not a plot summary.
              Good: "Postcolonial Fiction", "Southern Gothic", "War Literature",
                    "Magic Realism", "Psychological Fiction"


---
## SECTION PERIOD — Category 3: Period
---

PERIOD-01: 0–2 period tags. Include only when the time period is a
            meaningful part of the book's subject.

PERIOD-02: Use period tags when:
            - The period is the subject ("Cold War", "Victorian Era")
            - The book's argument depends on a specific era

PERIOD-03: Do NOT use a period tag when:
            - The period is obvious from the subject ("Ancient Greek
              Philosophy" does not also need "Ancient")
            - The period is incidental

PERIOD-04: Preferred period terms (use these forms for consistency):
            Ancient, Medieval, Early Modern, Renaissance, Enlightenment,
            Victorian Era, 19th Century, Early 20th Century, World War I,
            Interwar Period, World War II, Cold War, Postwar,
            Late 20th Century, Contemporary, Colonial America

PERIOD-05: Specific named periods (Cold War, World War II, Reconstruction,
            The Troubles, Colonial America) are preferable to bare century
            labels when they fit.


---
## SECTION GEO — Category 4: Geography
---

GEO-01: 0–2 geography tags. Include only when geography is a meaningful
         part of the book's subject.

GEO-02: Use standard English names. Title Case.
          Good: "United States", "Soviet Union", "Sub-Saharan Africa",
                "Latin America", "British Isles", "Southeast Asia"
          Bad:  "USA", "USSR", "Africa" (too broad unless truly global)

GEO-03: Do NOT include geography when:
          - The geography is incidental rather than central
          - The book is genuinely global or covers many regions

GEO-04: When in doubt, omit the geography tag. Wrong geography degrades
         search quality more than a missing one.


---
## SECTION FORMAT — Tag Formatting Rules
---

FORMAT-01: All tags are Title Case. Every significant word capitalised.
            Minor words (a, an, the, of, in, and, for, to) lowercase
            unless they begin the tag.

FORMAT-02: No tags longer than 4 words.

FORMAT-03: No commas within a tag.

FORMAT-04: Use ampersand (&) only when it is the conventional form
            (e.g., "Arts & Crafts"). Do not use & as a space-saver.

FORMAT-05: Prefer established conventional names: "Cold War" not
            "US-Soviet Rivalry". "Post-Apocalyptic" not "Post Apocalyptic".
            Hyphenate compound modifiers when conventional: "Coming-of-Age
            Fiction", "Post-Apocalyptic", "Hard-Boiled".


---
## SECTION GEN — Output Format & General Behaviour
---

GEN-01: Return a JSON array, one object per book, in the SAME ORDER as input.

GEN-02: Each object must have exactly these keys:
         {
           "id": <integer>,
           "tags": ["Tag One", "Tag Two", ...],
           "confidence": "high" | "medium" | "low",
           "notes": "<one short sentence>"
         }

GEN-03: "tags" is a flat JSON array of strings. 4–8 strings. No nesting,
         no category labels, no prefixes in the output strings.

GEN-04: No markdown fences. No commentary outside the JSON array.

GEN-05: Treat each book independently.

GEN-06: "confidence":
          "high"   — LCC data present and subject is clear
          "medium" — LCC data partial or subject requires inference
          "low"    — No LCC data; tags derived from title/author/existing only

GEN-07: "notes" — one short sentence describing the primary source used
         or any notable caveat. If existing tags were largely kept, note
         that. If significant noise was dropped, note that.
