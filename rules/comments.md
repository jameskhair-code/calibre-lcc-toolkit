# Comments Enrichment Rules
# Literary Awards & Nominees Collection — MQG-04
#
# Rules for generating the book comments / description field.
# Output is plain prose per section; the tool wraps sections in HTML.
# Fiction and non-fiction use different sections — see STRUCT.


---
## SECTION SCOPE — What This Task Is
---

SCOPE-01: For each book, generate a structured comment to populate the
           Calibre "comments" (book description) field. The comment is
           assembled from several sections — which sections appear depends
           on whether the book is fiction or non-fiction (see STRUCT).

SCOPE-02: The collection is "Collection – Literary Awards and Nominees" — a
           personal library of ~5,000 books nominated for or that won major
           literary prizes.

SCOPE-03: You are generating library metadata for a specific reader. Tone,
           framing, and what to emphasise follow the Reader Profile. This is
           not a generic catalog entry. Read the Reader Profile before
           writing.

SCOPE-04: Use publicly available information: Library of Congress records,
           Wikipedia, Goodreads descriptions, publisher summaries, award
           archives, and reviews. Do not invent facts about the book.

SCOPE-05: If key information is uncertain, say so rather than guess. Do not
           fabricate specific facts (dates, names, award positions, plot
           details). Flag uncertainty in the "notes" field.

SCOPE-06: Goodreads warning — Goodreads descriptions are often written by
           publishers in PR voice ("luminous", "unforgettable", "tour de
           force"). Use them for plot facts, not for voice or judgment.
           Rewrite in the Reader Profile voice; do not paraphrase the PR.

SCOPE-07: Book identity check — if multiple books share a title, confirm
           you have the right one using author + publication year + the LCC
           summary (when provided). If you cannot confirm, mark confidence
           "low" and say so in notes. Do not blend two different books.


---
## SECTION STRUCT — Section Structure (Fiction vs Non-Fiction)
---

STRUCT-01: First, classify the book as fiction or non-fiction. Set the
           `book_type` field to "fiction" or "nonfiction".

             - Fiction includes novels, novellas, short story collections,
               poetry collections, plays, and graphic novels.
             - Non-fiction includes history, biography, memoir, essays,
               criticism, science, polemic, journalism, and reference.
             - Edge cases: literary memoir → nonfiction; autobiographical
               novel → fiction; narrative non-fiction → nonfiction;
               creative non-fiction → nonfiction.

STRUCT-02: Section sequence by type — in this order:

           NON-FICTION:
             1. The Book                       — always present
             2. The Argument                   — always present
             3. Something You Might Not Know   — CONDITIONAL (see STRUCT-04)
             4. Why Read It                    — always present
             5. Must-Read Score                — always present (0–10 + rationale)

           FICTION:
             1. The Story                      — always present
             2. What It's Really About         — always present
             3. Something You Might Not Know   — CONDITIONAL (see STRUCT-04)
             4. Why Read It                    — always present
             5. Must-Read Score                — always present (0–10 + rationale)

STRUCT-03: Each section is returned as plain-text prose in the corresponding
           JSON field. Do NOT include HTML in the JSON values — the tool
           wraps each section in the right header and paragraph tags.

STRUCT-04: "Something You Might Not Know" is CONDITIONAL:
             - Include it when there is a genuinely interesting fact the
               reader is unlikely to know — an unusual origin story, a
               controversy, a surprising reception history, an unexpected
               connection to events or people, an award context worth
               noting (won despite scandal, lost to X in a famous upset).
             - Return an empty string when nothing genuinely interesting
               comes to mind. Do not manufacture trivia.
             - When present, it should be the most surprising or memorable
               thing you know about this book.

STRUCT-05: Do not include section titles in the text. The tool adds headers.

STRUCT-06: Do not repeat the title or authors in the prose — they appear in
           Calibre separately.


---
## SECTION NFB — Non-Fiction Section 1: The Book
---

NFB-01: 3–4 sentences covering, in natural sequence:
          a) What kind of book it is (history, biography, polemic, memoir,
             science writing, criticism, etc.) and its core subject.
          b) The specific argument, thesis, or angle — not just the topic.
          c) Why it landed: what made it significant, what it changed or
             established, or what made it contested. This flows from the
             argument; it is not a separate "this is important" line.

NFB-02: Name the argument, not just the topic.
          Bad:  "Examines the history of nuclear deterrence."
          Good: "Argues that American nuclear strategy in the Cold War was
                 driven more by bureaucratic momentum than by coherent
                 strategic calculation — and that this was not an accident."

NFB-03: Do NOT open with "This book" or "In this book". Lead with the
          subject, the argument, or the person.

NFB-04: For biographies, the opener should signal the kind of biography:
          "A literary biography of…", "A political biography tracing…",
          "A short, opinionated life of…". Avoid the flat "A biography of X".


---
## SECTION NFA — Non-Fiction Section 2: The Argument
---

NFA-01: 2–3 sentences. This is the "more meat" section. Where NFB sketches
          the book, NFA gets specific about the case it makes.

NFA-02: Cover one or more of:
          - The central claim stated plainly, with its key supporting move
          - The evidence or method: archival research, original interviews,
            a single sustained reading of a primary source, statistical
            analysis, lived experience, etc.
          - Where the argument cuts against received wisdom, or where it
            consolidated an emerging consensus
          - How it was received — who attacked it, who adopted it, and
            whether it has held up

NFA-03: Be specific. "The book has been influential" is empty. "The
          'declensionist' framing it introduced became standard in the
          field within a decade" is useful.

NFA-04: If the argument is contested, name the main objection in one
          phrase. Do not paper over real disagreement to make the book
          sound uncontroversial.

NFA-05: For memoirs and narrative non-fiction without a thesis per se,
          this section instead covers: the through-line of the narrative,
          the formal choice (chronological, fragmented, braided, etc.),
          and what the author is doing that distinguishes the book from
          other memoirs in its territory.


---
## SECTION FST — Fiction Section 1: The Story
---

FST-01: 3–4 sentences covering, in natural sequence:
          a) What kind of novel/story/collection it is (literary novel,
             historical novel, speculative, crime, comic, linked stories,
             a play in three acts, etc.).
          b) The setting and the narrative shape — who, when, where, and
             the basic engine of the story. Avoid plot-summary tedium;
             one or two concrete details beat a synopsis.
          c) What is distinctive about the telling: the voice, the
             structure, the prose, the conceit — whatever a reader will
             notice in the first thirty pages.

FST-02: Do NOT open with "This novel" or "In this novel". Lead with the
          setting, the protagonist, the conceit, or the opening situation.

FST-03: Avoid identity-first openers. Do not write "A novel about a Black
          woman navigating…" as the opening move. If identity is genuinely
          central to the book's project, mention it — but start with what
          the book does or where it is set, not who it is about.

FST-04: For story collections and poetry: name the unifying preoccupation
          or formal approach, the standout pieces if any, and the range
          across the collection.

FST-05: No spoilers past the inciting situation. A reader picks up a
          comment to decide whether to read the book; do not give away
          the ending or the major reveal.


---
## SECTION FRA — Fiction Section 2: What It's Really About
---

FRA-01: 2–3 sentences. This is the "more meat" section for fiction. Where
          FST describes the surface (setting, plot engine, voice), FRA gets
          at what the book is actually doing under the hood.

FRA-02: Cover one or more of:
          - The central theme or preoccupation — what the writer is
            really wrestling with
          - The argument the fiction is making (most serious novels are
            making one, even when they pretend not to)
          - The literary tradition it belongs to or argues with
          - What the book is doing that separates it from competent
            commercial fiction in the same genre

FRA-03: This is what justifies the book's place in a prize-nominated
          collection. A literary novel that "is about a marriage" is
          really about something specific — name it.

FRA-04: Be honest about ambition. If a novel reaches for big themes and
          does not quite get them, the right phrase is "reaches for" or
          "attempts" — not "achieves" or "delivers".

FRA-05: Avoid the cliché taxonomy: "a meditation on loss", "an
          exploration of identity", "a story about what it means to be
          human". These are stickers, not analysis. Name the specific
          version of the theme that this book pursues.


---
## SECTION KNOW — Section 3: Something You Might Not Know
---

KNOW-01: CONDITIONAL — see STRUCT-04. Only include when genuinely interesting.

KNOW-02: Good candidates:
           - An unusual origin story for the book
           - A controversy about the argument, sources, or author
           - A surprising or ironic reception (loved in one country,
             reviled in another; a bestseller only after the author died;
             pulped on first publication, canonised a decade later)
           - An unexpected connection (the author's other career, a real
             event the fiction anticipated, a political reaction)
           - A structural or formal feature that genuinely distinguishes
             the book from others in its class
           - Award context worth noting: it won despite scandal; it lost
             to a famous book in a famous upset; the jury split publicly;
             the author refused the prize

KNOW-03: Bad candidates — do NOT include:
           - The author's nationality alone
           - Generic facts ("translated into 30 languages", "sold a
             million copies")
           - Facts already implied by the title or subject
           - Dull biographical notes ("grew up in…", "studied at…")
           - "It was nominated for the Booker" — the whole library is
             prize-nominated; this is not news

KNOW-04: 1–3 sentences. The shorter and punchier, the better.


---
## SECTION SELL — Section 4: Why Read It
---

SELL-01: 3–4 sentences. This is the sell — give the reader a specific
          reason to pick up THIS book. Where relevant, fold in the stakes:
          why it still matters, what you gain from reading it, what it
          does that nothing else does.

SELL-02: See Reader Profile for what "the sell" means for this particular
          reader. Be honest. If the book is demanding, slow, or uneven,
          acknowledge it and give a genuine reason it is worth the effort.

SELL-03: Every book gets a real sell attempt. There is no "skip" — the
          reader keeps books for a reason and wants to know what that
          reason might be. If a book has aged badly or never quite worked,
          the sell can be honest about that and still locate what is
          worth the time (the central chapter, the prose, the historical
          interest, the argument that has not been bettered).

SELL-04: Do not use: "must-read", "essential", "not to be missed",
          "offers insights", "provokes reflection", "will leave you
          thinking", "a must for any reader of…", "anyone interested in
          X should read this", "stunning", "luminous", "tour de force".

SELL-05: Lead with a specific reason. The stakes — why it still matters —
          belong here as the argument for reading it, not as a separate
          declaration.
           Good: "Read it because it remains the only account that…"
           Good: "Worth it for the central chapter alone, which does in
                  forty pages what other books take three hundred to attempt."
           Good: "If [specific thing] interests you, nothing does it
                  better, and the argument has held up better than its
                  critics predicted."
           Good: "Demanding in places — the middle section earns patience —
                  but the payoff is a fully worked argument that changes
                  how you think about [specific thing]."


---
## SECTION SCORE — Section 5: Must-Read Score
---

SCORE-01: Always present. Two fields: an integer 0–10 and a 1–2 sentence
           rationale.

SCORE-02: Calibration — be honest. The point of the scale is that 8s, 9s,
           and 10s mean something. If everything is an 8, the scale is
           useless.

             0–3   Historically significant, award-listed, or formally
                   interesting, but genuinely hard to recommend to a
                   general reader today. Read it if the specific subject
                   pulls you. Includes books that have aged badly, are
                   primarily of academic interest, or whose argument has
                   been superseded.

             4–6   Solid. Rewarding for the right reader. Not urgent but
                   not a waste of time. Most of the collection lives here.
                   A 6 is "yes, read it when you get to it."

             7–8   Worth prioritising. Strong argument or story, good
                   payoff-to-effort ratio, holds up well. An 8 is "move
                   this up the pile."

             9–10  Reserved for books that genuinely change how you think
                   about something, or that are close to irreplaceable on
                   their subject. A 10 is rare — the book that anyone
                   reading in this territory has to read.

SCORE-03: Score the book against the kind of reader described in the
           Reader Profile, not against a hypothetical general audience.
           A dense work of political philosophy can score high even though
           most readers would bounce off it; the rationale should make
           the audience clear.

SCORE-04: The rationale is 1–2 sentences and must do real work:
           - 1 sentence default: the single best reason for the score.
           - 2 sentences when the score needs a caveat ("Demanding in
             the middle third — but the central argument is irreplaceable,
             so 8 rather than 6.").
           - Do NOT use the rationale as a second "Why Read It." The
             sell already does the long work; the rationale is the punchy
             summary of where this book sits on the scale.

SCORE-05: When confidence is "low" (see CONF), score conservatively —
           lean toward the middle (5–6) rather than guess high. Note the
           uncertainty in the rationale ("Provisional 6 pending closer
           look — limited reception information available.").


---
## SECTION CONF — Confidence Levels
---

CONF-01: "high" — Specific, verifiable information from multiple sources.
          All required sections can be written with concrete, accurate
          content. Author, title, plot/argument, reception are all clear.

CONF-02: "medium" — Good information for most sections; at least one
          relies on inference, a single source, or a description that
          could not be fully verified. Use this when the book is real
          and identifiable but reception/argument detail is thin.

CONF-03: "low" — Limited information, significant uncertainty about the
          book's argument, reception, or key facts, OR an identity
          ambiguity (multiple books share the title and you are not
          fully sure which one this is). Write what can be said
          confidently; note gaps in the "notes" field; score
          conservatively.


---
## SECTION GEN — Output Format & General Behaviour
---

GEN-01: Return a JSON array, one object per book, in the SAME ORDER as
         input.

GEN-02: Each object must have exactly these keys:
         {
           "id": <integer>,
           "book_type": "fiction" | "nonfiction",
           "the_book":              "<plain prose — non-fiction only; empty string for fiction>",
           "the_argument":          "<plain prose — non-fiction only; empty string for fiction>",
           "the_story":             "<plain prose — fiction only; empty string for non-fiction>",
           "what_its_really_about": "<plain prose — fiction only; empty string for non-fiction>",
           "something_you_might_not_know": "<plain prose, or empty string>",
           "why_read_it":           "<plain prose>",
           "must_read_score":       <integer 0–10>,
           "must_read_rationale":   "<1–2 sentences>",
           "confidence":            "high" | "medium" | "low",
           "notes":                 "<one short sentence — main caveat or key evidence>"
         }

GEN-03: Do NOT include HTML tags in any JSON string value. Plain prose
         only. The tool adds headers and paragraph wrappers automatically.

GEN-04: No markdown fences. No commentary outside the JSON array.

GEN-05: Treat each book independently. Do not borrow context from other
         books in the same batch.

GEN-06: Never fabricate specific facts. If uncertain, use hedged language
         or flag in notes. Lower the score and the confidence rather than
         guessing.

GEN-07: "notes" is one short sentence: the key evidence used or the main
         caveat. If multiple notes are needed, separate with semicolons.
         Examples: "Wikipedia summary used; central argument not
         independently verified." / "Two books share this title; matched
         on author and 1987 publication date."

GEN-08: Use the LCC summary, when provided, as a disambiguator and as a
         signal of subject and genre. It is not a source for plot detail
         but it helps confirm you have the right book and the right
         category.
