# Tag Enrichment Rules
# Literary Awards & Nominees Collection — MQG-05
#
# Rules for generating flat subject tags per book.
# Tags replace existing tags — they are not merged.
# Rules are grouped by category and numbered for reference.


---
## SECTION SCOPE — What This Task Is
---

SCOPE-01: For each book, generate a flat list of 4–8 tags drawn from
           four category types: Form, Subject, Period, and Geography.
           Not every category must be represented — use only what is
           genuinely applicable.

SCOPE-02: Tags are the primary search surface for this library. A reader
           searching for "Cold War" or "Biography" expects to find all
           relevant books. Accuracy and consistency matter more than
           comprehensiveness.

SCOPE-03: Source material in priority order:
             1. lcc_secondary_class — the most reliable subject signal
             2. lcc_summary — the specific argument and subject
             3. lcc_primary_class — broad class fallback
             4. Title and authors — use when LCC data is absent

SCOPE-04: Do not repeat the LCC hierarchy verbatim as tags. Translate it
           into readable, searchable strings.
            Bad:  "HD - Industries & Land Use & Labor"
            Good: "Labor History", "Economic History"

SCOPE-05: Do not add award names as tags. Award data lives in other fields.

SCOPE-06: Do not add the author's name or nationality as a tag.


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
             Derive from lcc_secondary_class and lcc_summary.

SUBJECT-02: Subject tags are Title Case noun phrases. No articles at the
             start ("History of X" not "The History of X"). No verbs.
              Good: "Military History", "Cold War", "Public Health",
                    "Urban Planning", "Slavery", "Nuclear Weapons"
              Bad:  "About the Cold War", "examining military history"

SUBJECT-03: Be specific enough to be useful, not so specific that only one
             book would ever match.
              Too broad:  "History"  (use the Form tag for that)
              Too narrow: "Soviet Naval Strategy 1943–1945"
              Right:      "Naval History", "World War II", "Soviet Military"

SUBJECT-04: Do not duplicate the Form tag as a subject tag.
              Bad:  Form="Biography", Subject="Biography"
              Good: Form="Biography", Subject="Political Biography" or
                    just name the relevant subject field

SUBJECT-05: For literature (novels, poetry, short stories), the subject
             tags describe the work's themes or the tradition it belongs to,
             not a plot summary.
              Good: "Postcolonial Fiction", "Southern Gothic", "War Literature",
                    "Magic Realism", "Psychological Fiction"


---
## SECTION PERIOD — Category 3: Period
---

PERIOD-01: 0–2 period tags. Include only when the time period is a
            meaningful part of the book's subject — not just when events
            happen to take place in a century.

PERIOD-02: Use period tags when:
            - The period is the subject ("Cold War" is a period AND a subject;
              "Victorian Era" as context for a social history)
            - The book's argument depends on a specific era

PERIOD-03: Do NOT use a period tag when:
            - The period is obvious from the subject ("Ancient Greek Philosophy"
              does not also need "Ancient")
            - The period is incidental (a biography whose subject happened to
              live in the 19th century but the book is not about that era)

PERIOD-04: Preferred period terms (use these forms for consistency):
            Ancient, Medieval, Early Modern, Renaissance, Enlightenment,
            Victorian Era, 19th Century, Early 20th Century, World War I,
            Interwar Period, World War II, Cold War, Postwar, Late 20th Century,
            Contemporary

PERIOD-05: Specific named periods (Cold War, World War II, Reconstruction,
            The Troubles) are preferable to bare century labels when they fit.


---
## SECTION GEO — Category 4: Geography
---

GEO-01: 0–2 geography tags. Include only when geography is a meaningful
         part of the book's subject — not just the author's nationality
         or the setting.

GEO-02: Use standard English names for countries and regions. Title Case.
          Good: "United States", "Soviet Union", "Sub-Saharan Africa",
                "Latin America", "British Isles", "Southeast Asia"
          Bad:  "USA", "USSR", "Africa" (too broad unless the book genuinely
                covers the whole continent)

GEO-03: Do NOT include geography when:
          - The lcc_secondary_class already implies it clearly (e.g., DK
            implies Russia; no need to add a Russia tag)
          - The geography is incidental rather than central to the argument
          - The book is genuinely global or covers many regions without focus

GEO-04: When in doubt, omit the geography tag. A wrong geography tag
          degrades search quality more than a missing one.


---
## SECTION FORMAT — Tag Formatting Rules
---

FORMAT-01: All tags are Title Case. Every significant word capitalised.
            Minor words (a, an, the, of, in, and, for, to) lowercase
            unless they begin the tag.
             Good: "History of Science", "Law of Nations"
             Bad:  "history of science", "HISTORY", "Law Of Nations"

FORMAT-02: No tags longer than 4 words. If a subject requires more words
            to be accurate, find a shorter conventional name.

FORMAT-03: No commas within a tag. Tags are comma-separated in the output —
            a comma inside a tag string would corrupt the field.

FORMAT-04: Use ampersand (&) only when it is the conventional form of the
            name (e.g., "Arts & Crafts"). Do not use & as a space-saver.

FORMAT-05: Prefer established conventional names over invented ones.
            "Cold War" not "US-Soviet Rivalry". "Victorian Era" not
            "Mid-19th Century Britain".


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
          "low"    — No LCC data; tags derived from title/author only

GEN-07: "notes" — one short sentence describing the primary source used
         or any notable caveat.
          Example: "Tags derived from LCC secondary class and summary."
          Example: "Form tag uncertain — classified as History but subject
                    straddles biography and political science."
