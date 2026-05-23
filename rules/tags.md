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

SCOPE-03: Evidence in strict priority order — stop when you have enough signal:
             1. lcc_secondary_class — most reliable subject signal;
                maps directly to subject and sub-genre tags
             2. lcc_summary — the specific argument/content of this book;
                use to confirm or refine secondary class interpretation
             3. lcc_primary_class — broad class only; use as fallback
                when secondary is absent or too generic (e.g. "PS - Individual authors")
             4. current_tags — review and reuse accurate ones;
                normalize form but preserve meaning
             5. Title and authors — last resort when LCC data is absent;
                document in notes that tags are title-derived

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

FORMAT-02: No tags longer than 4 words. (Enforced programmatically —
            tags exceeding this limit will be truncated automatically.)

FORMAT-03: No commas within a tag. (Enforced programmatically — any
            comma causes the text before it to be taken as the full tag.)

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


---
## SECTION CONF — Confidence Calibration
---

CONF-01: Return "high" when ALL of the following hold:
           - lcc_secondary_class is present and unambiguous
           - Form tag selection is obvious (not a judgment call)
           - 5+ strong subject signals are available across LCC data,
             lcc_summary, and existing tags

CONF-02: Return "medium" when ANY of the following apply:
           - LCC data is present but thin (primary class only, no secondary)
           - Form tag required a judgment call (e.g. Nonfiction fallback,
             Memoir vs. Autobiography, Journalism vs. History)
           - Fewer than 3 clear subject signals available
           - lcc_summary conflicts with existing tags and resolution is uncertain

CONF-03: Return "low" when ANY of the following apply:
           - No LCC data at all
           - Title is generic (e.g. "The Stories", "Collected Works")
           - Subject is derived entirely from title/author with no LCC support
           - Fewer than 2 signals total for any non-Form tag proposed

CONF-04: When the Python validator corrects a Form tag issue (zero or
          multiple Form tags returned), confidence is automatically downgraded
          to "medium" regardless of what you returned. The notes field will
          record the issue.


---
## SECTION RISK — Edge Cases and Defensive Behaviour
---

RISK-01: Thin data → minimal tags.
           No LCC + no existing tags + generic title: return low confidence
           with only a Form tag (best guess) and at most 1–2 subject tags
           derived from the title. Do not pad to reach the 4–8 minimum.
           Document the limitation in notes.

RISK-02: Sub-genre always requires its parent.
           "Space Opera" requires "Science Fiction" alongside it.
           "Epic Fantasy" requires "Fantasy". "Psychological Thriller"
           requires "Thriller". When you are confident in a sub-genre,
           include the parent — do not make the reader guess the umbrella.
           Exception: if you are not confident even in the parent, do not
           include either.

RISK-03: Borderline Form choices → document them.
           Biography vs. Memoir vs. Nonfiction, Journalism vs. History,
           Literary Criticism vs. Philosophy — when these are judgment calls,
           state in notes why you chose as you did. This allows manual
           correction to be targeted.

RISK-04: When uncertain about any tag, omit it.
           It is better to return 4 accurate tags than 7 tags where 3 are
           guesses. A missed tag is correctable in a later pass. A wrong
           tag degrades search quality for every user of this library.


---
## SECTION EXAMPLES — Reference Input/Output Pairs
---

EXAMPLE-01: Fiction, strong LCC, clear genre

  Input:
    title: "The Left Hand of Darkness"
    authors: "Ursula K. Le Guin"
    lcc: "PS3562.E42 L4"
    lcc_primary_class: "PS - American Literature in English"
    lcc_secondary_class: "PS3562 - Individual authors: L"
    lcc_summary: "A science fiction novel exploring gender and society on an
                  alien world. Le Guin's most celebrated work."
    current_tags: ["Fiction", "science fiction", "gender"]

  Expected output:
    tags: ["Novel", "Science Fiction", "Feminist Science Fiction",
           "Speculative Fiction", "Anthropological Fiction"]
    confidence: "high"
    notes: "LCC PS confirmed fiction; sub-genre and themes from lcc_summary
            and existing tags. Dropped 'Fiction' (noise) and normalised
            'science fiction'."

EXAMPLE-02: Nonfiction, clear LCC, named period

  Input:
    title: "The Guns of August"
    authors: "Barbara W. Tuchman"
    lcc: "D521 .T8"
    lcc_primary_class: "D - World History and History of Europe, Asia, Africa, etc."
    lcc_secondary_class: "D501-680 - World War I"
    lcc_summary: "Narrative history of the opening weeks of World War I,
                  focusing on the decisions that led to catastrophe."
    current_tags: ["History", "World War I", "1914-1918"]

  Expected output:
    tags: ["History", "World War I", "Military History",
           "European History", "20th Century"]
    confidence: "high"
    notes: "LCC D521 confirms WWI military history. Dropped bare date range
            '1914-1918' (period name preferred). Added 'Military History' and
            'European History' from LCC secondary."

EXAMPLE-03: Ambiguous Form, thin LCC

  Input:
    title: "Consider the Lobster"
    authors: "David Foster Wallace"
    lcc: "PS3573.A425635 C66"
    lcc_primary_class: "PS - American Literature in English"
    lcc_secondary_class: "PS3573 - Individual authors: W"
    lcc_summary: "Essays on culture, politics, and literature by David
                  Foster Wallace."
    current_tags: ["essays", "Nonfiction"]

  Expected output:
    tags: ["Essay Collection", "Literary Criticism",
           "American Literature", "Contemporary"]
    confidence: "medium"
    notes: "PS class is author's literary home regardless of form; lcc_summary
            confirms essays. Form chosen as Essay Collection over Nonfiction.
            'Nonfiction' kept would duplicate Form meaning — dropped. LCC
            secondary is author-specific (no subject class), so subject tags
            are thin."
