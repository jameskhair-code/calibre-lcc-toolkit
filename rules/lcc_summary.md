# LCC Summary-Only Rules
# v1.7 item 5: when the OL catalog provides confirmed class fields,
# the AI is called only for the lcc_summary prose. Style guidance
# mirrors PATH-01 through PATH-06 in rules/lcc.md but the scope is
# narrower: no class fields, no confidence, no source — just the
# summary sentence.

---
## SECTION SUMMARY — One-Sentence Subject Summary
---

SUMMARY-01: Write a single complete sentence, typically 20–40 words.
            - Do NOT open with "This book..." — start with what the book
              does, examines, traces, or argues.
            - Use plain prose. No bullet separators, no semicolons, no
              " > ".

SUMMARY-02: Summarise from the provided `description` field. The
            description is authoritative source material (pre-fetched
            from Google Books or Open Library).
            - Do not introduce facts (dates, names, plot specifics,
              geographic setting) that are not stated or directly
              implied by the description, title, or authors.
            - For biographies, name the subject and the biographer's
              angle. Useful openers: "A literary biography of…", "A
              political biography tracing…", "The definitive life
              of…", "Examines the life of … through…".
            - If the description appears to describe a different work
              than the title/authors imply (identity mismatch), return
              an empty string for `lcc_summary` for that book — the
              caller will keep its template summary rather than write
              prose grounded in the wrong work.

SUMMARY-03: Do not repeat the primary or secondary class in broad
            terms — go straight to the specific subject.
            - Don't open with "military science" if Pri is
              "U - Military Science".
            - Don't open with "American literature" if Sec is
              "PS - American Literature".
            - The class fields already give the reader the broad
              area; the summary is for what's distinctive.

SUMMARY-04: Name time period and geography when they are genuinely
            distinctive and not already implied by the secondary class.
            - Include period when it IS the subject (Cold War,
              1945–1990).
            - Include geography when it IS the subject and not implied
              by the secondary class.
            - Omit geography already implied (DK already means Russia).
            - Omit period obvious from the call number year alone.

SUMMARY-05: Examples (catalog-confirmed class context + description →
            summary). Note: these examples mirror PATH-03 in
            rules/lcc.md so the style stays consistent across the two
            flows.

            LCC:    "DK189 .W67 2003"  Sec: "DK - Russia & Soviet Union & Former Republics"
            Summary: "Examines how the Romanov dynasty used court ceremony
                      and political myth to construct and project imperial
                      monarchical authority."
            (no geography phrase — DK already implies Russia)

            LCC:    "PS2123 .E25 1962"  Sec: "PS - American Literature"
            Summary: "A multi-volume literary biography of Henry James
                      tracing his expatriate London years and the
                      development of his major early-period fiction from
                      1870 to 1881."
            (biography — opens by naming the genre and subject)

            LCC:    "TX945.5.M33 C43 2020"  Sec: "TX - Home Economics"
            Summary: "How McDonald's franchise model became a vehicle for
                      Black economic participation — and exploitation — in
                      20th-century America."
