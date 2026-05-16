# Comments Enrichment Rules
# Literary Awards & Nominees Collection — MQG-04
#
# Rules for generating the book comments / description field.
# Three sections (four when the conditional fires).
# Output is plain prose per section; the tool wraps sections in HTML.


---
## SECTION SCOPE — What This Task Is
---

SCOPE-01: For each book, generate a structured comment to populate the
           Calibre "comments" (book description) field. The comment has
           three sections — four when the conditional section fires
           (see STRUCT section).

SCOPE-02: The collection is "Collection – Literary Awards and Nominees" — a
           personal library of ~5,000 books nominated for or that won major
           literary prizes.

SCOPE-03: You are generating library metadata for a specific reader. Tone
           and framing follow the Reader Profile. This is not a generic
           catalog entry.

SCOPE-04: Use publicly available information: Library of Congress records,
           Wikipedia, Goodreads descriptions, publisher summaries, award
           archives, and reviews. Do not invent facts about the book.

SCOPE-05: If key information is uncertain, say so rather than guess. Do not
           fabricate specific facts (dates, names, award positions).


---
## SECTION STRUCT — Section Structure
---

STRUCT-01: The comment contains these sections, in order:

             1. The Book                       — always present
             2. Something You Might Not Know   — CONDITIONAL (see STRUCT-04)
             3. Why Read It                    — always present

STRUCT-02: Each section is returned as plain-text prose in the corresponding
           JSON field. Do NOT include HTML in the JSON values — the tool
           wraps each section in <h3> and <p> tags automatically.

STRUCT-03: Do not include section titles in the text. The tool adds headers.

STRUCT-04: "Something You Might Not Know" is CONDITIONAL:
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

BOOK-01: 3–5 sentences covering three things in natural sequence:
           a) What kind of book it is (history, biography, novel, polemic...)
              and its core subject or narrative
           b) The specific argument, thesis, or story — not just the topic
           c) Why it landed: what made it significant, what it changed or
              established, or what made it contested

BOOK-02: The significance beat (c) should flow naturally from the argument
          (b) — it is not a separate "this book is important" declaration.
          It is the consequence or reception of the argument.
           Good: "...a reading that most scholars have since accepted."
           Good: "...which made it deeply uncomfortable for several
                  governments when it appeared."
           Good: "...the first account to make this argument to a general
                  audience, and the one no subsequent treatment has displaced."
           Bad:  "This is an important and significant contribution to
                  the field."

BOOK-03: Do NOT open with "This book" or "In this book". Lead with the
          subject, the argument, or the person.

BOOK-04: Do NOT repeat the title or authors — they appear in Calibre
          separately.

BOOK-05: Name the argument, not just the topic.
           Bad:  "Examines the history of nuclear deterrence."
           Good: "Argues that American nuclear strategy in the Cold War was
                  driven more by bureaucratic momentum than by coherent
                  strategic calculation — and that this was not an accident."


---
## SECTION KNOW — Section 2: Something You Might Not Know
---

KNOW-01: CONDITIONAL — see STRUCT-04. Only include when genuinely interesting.

KNOW-02: Good candidates:
           - An unusual origin story for the book
           - A controversy about the argument or sources
           - A surprising or ironic reception (loved in one country, reviled
             in another; a bestseller only after the author died)
           - An unexpected connection (the author's other career, a real event
             the fiction anticipated, a political reaction)
           - A structural or formal feature that genuinely distinguishes
             the book from others in its class

KNOW-03: Bad candidates — do NOT include:
           - The author's nationality alone
           - Generic facts ("translated into 30 languages")
           - Facts already implied by the title or subject
           - Dull biographical notes ("grew up in...")

KNOW-04: 1–3 sentences. The shorter and punchier, the better.


---
## SECTION SELL — Section 3: Why Read It
---

SELL-01: 3–5 sentences. This is the sell — give the reader a specific reason
          to pick up this book. Where relevant, fold in the stakes: why it
          still matters, what you gain from reading it, what it does that
          nothing else does.

SELL-02: See Reader Profile for what "the sell" means for this particular
          reader. Be honest. If the book is demanding, slow, or uneven,
          acknowledge it and give a genuine reason it is worth the effort.

SELL-03: Do not use: "must-read", "essential", "not to be missed",
          "offers insights", "provokes reflection", "will leave you thinking",
          "a must for any reader of...", "anyone interested in X should read."

SELL-04: Lead with a specific reason. The stakes — why it still matters —
          belong here as the argument for reading it, not as a separate
          declaration.
           Good: "Read it because it remains the only account that..."
           Good: "Worth it for the central chapter alone, which does
                  in forty pages what other books take three hundred to
                  attempt."
           Good: "If [specific thing] interests you, nothing does it better,
                  and the argument has held up better than its critics
                  predicted."
           Good: "Demanding in places — the middle section earns patience —
                  but the payoff is a fully worked argument that changes how
                  you think about [specific thing]."


---
## SECTION CONF — Confidence Levels
---

CONF-01: "high" — Specific, verifiable information from multiple sources.
          All three sections can be written with concrete, accurate content.

CONF-02: "medium" — Good information for most sections; at least one relies
          on inference or limited sources.

CONF-03: "low" — Limited information, or significant uncertainty about the
          book's argument, reception, or key facts. Write what can be said
          confidently; note gaps in the "notes" field.


---
## SECTION GEN — Output Format & General Behaviour
---

GEN-01: Return a JSON array, one object per book, in the SAME ORDER as input.

GEN-02: Each object must have exactly these keys:
         {
           "id": <integer>,
           "the_book": "<plain prose — no HTML tags>",
           "something_you_might_not_know": "<plain prose, or empty string>",
           "why_read_it": "<plain prose — no HTML tags>",
           "confidence": "high" | "medium" | "low",
           "notes": "<one short sentence — main caveat or key evidence>"
         }

GEN-03: Do NOT include HTML tags in any JSON string value. Plain prose only.
         The tool adds <h3> and <p> wrappers automatically.

GEN-04: No markdown fences. No commentary outside the JSON array.

GEN-05: Treat each book independently. Do not borrow context from other books
         in the same batch.

GEN-06: Never fabricate specific facts. If uncertain, use hedged language or
         flag in notes.

GEN-07: "notes" is one short sentence: the key evidence used or the main
         caveat. Example: "Wikipedia summary used; central argument not
         independently verified."
