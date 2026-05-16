# Comments Enrichment Rules
# Literary Awards & Nominees Collection — MQG-04
#
# Rules for generating the book comments / description field.
# Output is plain prose per section; the tool wraps sections in HTML.
# Rules are grouped by category and numbered for reference.


---
## SECTION SCOPE — What This Task Is
---

SCOPE-01: For each book, generate a structured comment to populate the
           Calibre "comments" (book description) field. The comment
           consists of 5 or 6 sections (see STRUCT section).

SCOPE-02: The collection is "Collection – Literary Awards and Nominees" — a
           personal library of ~5,000 books nominated for or that won major
           literary prizes. Award context is always relevant.

SCOPE-03: You are generating library metadata for a specific reader. Tone
           and framing follow the Reader Profile. This is not a generic
           catalog entry.

SCOPE-04: Use publicly available information: Library of Congress records,
           Wikipedia, Goodreads descriptions, publisher summaries, award
           archives, and reviews. Do not invent facts about the book.

SCOPE-05: If your information is uncertain — for example you know the book
           was shortlisted but not the exact year — say so rather than guess.
           Do not fabricate award positions or years.


---
## SECTION STRUCT — Section Structure
---

STRUCT-01: The comment must contain these sections, in order:

             1. The Book                       — always present
             2. Why It Matters                 — always present
             3. Award Context                  — always present
             4. Something You Might Not Know   — CONDITIONAL (see STRUCT-05)
             5. Why Read It                    — always present
             6. Source Notes                   — always present

STRUCT-02: Each section is returned as plain-text prose in the corresponding
           JSON field. Do NOT include HTML in the JSON values — the tool
           wraps each section in <h3> and <p> tags automatically.

STRUCT-03: Do not include section titles in the text. The tool adds headers.

STRUCT-04: Each section should be a single paragraph. Length guidance:
             - The Book:                    2–4 sentences
             - Why It Matters:              2–3 sentences
             - Award Context:               1–3 sentences
             - Something You Might Not Know: 1–3 sentences (if present)
             - Why Read It:                 2–3 sentences
             - Source Notes:                1–2 sentences

STRUCT-05: "Something You Might Not Know" is CONDITIONAL:
             - Include it when there is a genuinely interesting fact the
               reader is unlikely to know — an unusual origin story, a
               controversy, a surprising reception history, an unexpected
               connection to events or people.
             - Return an empty string when nothing genuinely interesting
               comes to mind. Do not manufacture trivia.
             - When present, it should be the most surprising or memorable
               thing you know about this book.


---
## SECTION BOOK — Section 1: The Book
---

BOOK-01: Cover:
           - What kind of book it is (history, biography, novel, essay
             collection, reportage, polemic...)
           - The core subject or narrative (what it is actually about)
           - The key people, places, period, or argument that define it

BOOK-02: Do NOT open with "This book" or "In this book". Lead with the
          subject or the argument.

BOOK-03: Do NOT repeat the title or authors — they appear in Calibre
          separately.

BOOK-04: Every sentence should add information. Avoid empty openers.
           Bad:  "A compelling exploration of the history of..."
           Good: "Traces three centuries of German drainage and river
                  engineering, arguing that the conquest of wetlands was
                  central to the making of modern German national identity."

BOOK-05: If the book has a specific central argument (not just a topic),
          state the argument, not just the topic.
           Bad:  "Examines the history of nuclear deterrence."
           Good: "Argues that American nuclear strategy in the Cold War was
                  driven more by bureaucratic momentum than by coherent
                  strategic calculation."


---
## SECTION MATTERS — Section 2: Why It Matters
---

MATTERS-01: Why was this book significant in its field or for its readers?
             What did it change, establish, or challenge?

MATTERS-02: This can be scholarly, cultural, or political significance —
             whatever is most genuine for this particular book.

MATTERS-03: Avoid generic statements. Name the specific contribution.
              Bad:  "A landmark work in the history of science."
              Good: "The first popular account to argue that the 1954 Salk
                     vaccine trials were as much about Cold War politics as
                     about public health — a reading that later scholarship
                     confirmed."

MATTERS-04: If the book was controversial or received with resistance, that
             is often a more interesting "why it matters" than a polite note
             about scholarly contribution.


---
## SECTION AWARD — Section 3: Award Context
---

AWARD-01: Always include this section. The book is in a literary awards
           collection — its award history is part of its identity in this
           library.

AWARD-02: State the award(s), year, and outcome (won / shortlisted /
           longlisted / nominated).
            Examples:
              "Shortlisted for the Booker Prize in 1984."
              "Won the Pulitzer Prize for General Nonfiction in 1998."
              "Longlisted for the National Book Award, Biography, 2003."

AWARD-03: If the award year or position is uncertain, say so clearly rather
           than guessing.
            Example: "Listed among Booker Prize nominees in the early 1990s —
                      exact year not confirmed."

AWARD-04: If the book's presence on a shortlist was itself surprising,
           or if the award is a lesser-known prize worth explaining briefly,
           add a sentence of context.

AWARD-05: Use tag and series data from the input to identify the award.
           If the information is absent or ambiguous, derive it from the
           title, author, and publication date if possible, or note uncertainty.


---
## SECTION KNOW — Section 4: Something You Might Not Know
---

KNOW-01: CONDITIONAL — see STRUCT-05. Only include when genuinely interesting.

KNOW-02: Good candidates:
           - An unusual origin story for the book
           - A controversy about the argument or sources
           - A surprising or ironic reception (loved in one country, reviled
             in another; a bestseller only after the author died)
           - An unexpected connection (an author's other career, a real event
             the fiction anticipated, a political reaction)
           - A structural or formal feature that distinguishes the book

KNOW-03: Bad candidates — do NOT include:
           - The author's nationality alone
           - Generic facts ("translated into 30 languages")
           - Facts already implied by the title or subject
           - Dull biographical notes ("grew up in...")

KNOW-04: 1–3 sentences. The shorter and punchier, the better.


---
## SECTION SELL — Section 5: Why Read It
---

SELL-01: Give a specific reason to pick up this book. See Reader Profile
          for what "the sell" means for this particular reader.

SELL-02: Be honest. If the book is demanding, slow, or uneven in places,
          acknowledge it and give a genuine reason it is worth the effort.

SELL-03: Do not use: "must-read", "essential", "not to be missed",
          "a must for any reader of...", "offers insights",
          "provokes reflection", "will leave you thinking."

SELL-04: Lead with a specific reason:
           "Read it because it is the only account that..."
           "Worth it for [specific passage / argument / scene] alone."
           "If [specific thing] interests you, nothing does it better."
           "Infuriating in places, but the argument in Chapter X makes
            the whole book worthwhile."


---
## SECTION SOURCE — Section 6: Source Notes
---

SOURCE-01: 1–2 sentences. Briefly describe what sources informed the comment.
             Examples:
               "Generated from Library of Congress catalog records,
                Wikipedia, and publisher descriptions."
               "Generated using Wikipedia, Goodreads, and the Booker Prize
                archive. Award year confirmed via prize website."

SOURCE-02: Be transparent about AI generation. Do not write this as if it
            were human research notes.

SOURCE-03: If key information was absent or uncertain, note the gap:
            "Award year not independently confirmed — based on available
             prize lists."


---
## SECTION CONF — Confidence Levels
---

CONF-01: "high" — Strong, specific information available from multiple
          sources. All five sections can be written with verifiable content.
          Award history is confirmed.

CONF-02: "medium" — Reasonable information for most sections, but at least
          one relies on inference or limited sources. Award year or position
          may be approximate.

CONF-03: "low" — Limited information found, or significant uncertainty about
          award history, publication details, or the book's core argument.
          Write what can be said with confidence; flag the gaps in notes.


---
## SECTION GEN — Output Format & General Behaviour
---

GEN-01: Return a JSON array, one object per book, in the SAME ORDER as input.

GEN-02: Each object must have exactly these keys:
         {
           "id": <integer>,
           "the_book": "<plain prose — no HTML tags>",
           "why_it_matters": "<plain prose — no HTML tags>",
           "award_context": "<plain prose — no HTML tags>",
           "something_you_might_not_know": "<plain prose, or empty string>",
           "why_read_it": "<plain prose — no HTML tags>",
           "source_notes": "<plain prose — no HTML tags>",
           "confidence": "high" | "medium" | "low",
           "notes": "<one short sentence — main caveat or key fact used>"
         }

GEN-03: Do NOT include HTML tags in any JSON string value. Plain prose only.
         The tool adds <h3> and <p> wrappers automatically.

GEN-04: No markdown fences. No commentary outside the JSON array.

GEN-05: Treat each book independently. Do not borrow context or award details
         from other books in the same batch.

GEN-06: Never fabricate specific facts (dates, award years, locations, names).
         If uncertain, use hedged language or flag in notes.

GEN-07: "notes" is one short sentence: the main caveat or the key evidence
         used. Keep it concise.
          Example: "Award year confirmed via Booker Prize archive."
          Example: "Wikipedia summary used — independent verification of
                    central argument not attempted."
