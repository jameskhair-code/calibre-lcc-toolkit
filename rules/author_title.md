# Author & Title Cleanup Rules
# Literary Awards & Nominees Collection
#
# Rules are grouped by category and numbered for reference.
# Add, remove, or edit rules here — no code changes required.
# Confidence guide: apply "high" only when a rule is mechanical and unambiguous.


---
## SECTION T-CAP — Title Capitalization
---

T-CAP-01: Use title case for all titles. Capitalise the first and last word of the
           title regardless of part of speech.

T-CAP-02: Capitalise all major words: nouns, verbs, adjectives, adverbs.

T-CAP-03: Lowercase minor words in the middle of a title: articles (a, an, the),
           coordinating conjunctions (and, but, or, nor, for, yet, so),
           and short prepositions (at, by, for, in, of, on, to, up, as).

T-CAP-04: Prepositions of five or more letters are capitalised
           (About, Above, Across, After, Against, Along, Among, Around, Before,
           Behind, Below, Beneath, Beside, Between, Beyond, During, Inside,
           Outside, Through, Throughout, Under, Until, Within, Without).

T-CAP-05: The first word after a colon or em-dash is always capitalised,
           even if it would normally be lowercase.

T-CAP-06: Hyphenated compound words: capitalise both parts
           (e.g. "Self-Made", "Well-Known", "Long-Term").

T-CAP-07: Do NOT alter the capitalisation of proper nouns, trademarked names,
           or invented words (e.g. iPhone, eBay, McCourt, O'Brien).

T-CAP-08: Do NOT alter the capitalisation of foreign-language words or titles.
           Apply English title-case rules only to English-language titles.

T-CAP-09: Titles in ALL CAPS should be converted to title case
           (e.g. "THE ROAD" → "The Road").

T-CAP-10: Titles in all lowercase should be converted to title case
           (e.g. "the remains of the day" → "The Remains of the Day"),
           UNLESS the author intentionally uses lowercase as a stylistic choice
           (e.g. bell hooks — author name, not title).


---
## SECTION T-AWD — Title: Award & Marketing Markers
---

T-AWD-01: Remove any text identifying the book as a prize winner or nominee,
           enclosed in parentheses, brackets, or following a separator.
           Examples to remove:
             "(Winner of the Booker Prize)"
             "(Booker Prize Winner)"
             "[Man Booker Prize]"
             "- Winner of the National Book Award"
             "(Pulitzer Prize Winner)"
             "(Nobel Prize)"
             "(Costa Award Winner)"
             "(Orange Prize)"
             "(Women's Prize for Fiction)"

T-AWD-02: Remove award shortlist/longlisted markers:
             "(Booker Prize Shortlist)"
             "(Longlisted for the Booker Prize)"
             "(Man Booker Longlist)"

T-AWD-03: Remove award year markers embedded with award names:
             "(2019 Booker Prize Winner)"
             "[Booker Prize 2001]"

T-AWD-04: Remove generic marketing phrases appended to titles:
             "A New York Times Bestseller"
             "A #1 New York Times Bestseller"
             "An Instant Bestseller"
             "A National Bestseller"
             "Now a Major Motion Picture"
             "Now a Major TV Series"
             "Soon to Be a Major Film"

T-AWD-05: Remove critical praise snippets embedded in the title field:
             "\"Extraordinary\" — The Guardian"
             "The Book Everyone Is Talking About"

T-AWD-06: Remove publisher marketing suffixes:
             "(A Novel of the Year)"
             "(Oprah's Book Club)"
             "(Reese's Book Club Pick)"


---
## SECTION T-EDT — Title: Edition & Publication Markers
---

T-EDT-01: Remove edition markers that are not integral to the title:
             "(Revised Edition)"
             "(Revised and Updated Edition)"
             "(Updated Edition)"
             "(Expanded Edition)"
             "(New Edition)"
             "(Second Edition)" / "(2nd Edition)" / "(2nd ed.)"
             "(Third Edition)" / "(3rd Edition)"
             "(Anniversary Edition)"
             "(Centenary Edition)"
             "(Commemorative Edition)"
             "Revised and Updated"  (when appended as a suffix)

T-EDT-02: EXCEPTION — keep edition language if it is genuinely part of the
           published title (e.g. "The Annotated Waste Land with Eliot's
           Contemporary Prose" — "Annotated" is integral).
           Use "medium" confidence when unsure.

T-EDT-03: Remove delivery-format indicators — these describe how the same
           content is packaged, not a distinct work:
             "(Audiobook)"
             "(Unabridged)"
             "(Abridged)"
             "(Large Print)"
             "(Kindle Edition)"
             "(eBook)"
             "(Trade Paperback)"
           EXCEPTION — do NOT remove adaptation markers that identify a
           genuinely different creative work. Keep these as-is:
             "(Graphic Novel)"
             "(Illustrated Edition)"
             "(Film Tie-In)"
             "(Manga)"
             "(Comic)"
           Removing an adaptation marker could make the title identical to the
           source work, causing a collision in the library. Use "medium"
           confidence if unsure whether a marker is a format or an adaptation.
           WRONG: "The Handmaid's Tale (Graphic Novel)"  →  "The Handmaid's Tale"
           RIGHT: "The Handmaid's Tale (Graphic Novel)"  →  "The Handmaid's Tale (Graphic Novel)"

T-EDT-04: Remove "With a New Introduction by [Name]" and similar additions.

T-EDT-05: Remove "With a New Afterword", "With a New Preface", etc.

T-EDT-06: Remove "Originally Published as [Title]" annotations.


---
## SECTION T-SUB — Title: Subtitles
---

T-SUB-01: Preserve substantive subtitles — those that add specific meaning
           about the book's subject matter.
           Example to KEEP: "The Warmth of Other Suns: The Epic Story of
           America's Great Migration"

T-SUB-02: Remove generic subtitles that add no meaningful information.
           Matching is case-insensitive — remove regardless of capitalisation.
           Patterns to remove (the colon and everything after):
             ": A Novel"  /  ": a Novel"  /  ": a novel"
             ": A Memoir"
             ": A Story"
             ": Stories"
             ": Essays"
             ": Poems"
             ": A Collection"
             ": A Life"
             ": A Biography"
             ": A History"
             ": Nonfiction"
             ": Fiction"
           WRONG: "Halcyon: A novel"  →  "Halcyon: A Novel"  (capitalising ≠ removing)
           RIGHT: "Halcyon: A novel"  →  "Halcyon"
           WRONG: "The Garden: a memoir"  →  "The Garden: A Memoir"
           RIGHT: "The Garden: a memoir"  →  "The Garden"
           Do NOT capitalise the subtitle word and leave it — always remove the
           entire ": A <generic-word>" phrase entirely.

T-SUB-03: When in doubt about a subtitle's value, retain it and use
           "medium" or "low" confidence. Do not remove subtitles
           unless you are certain they are generic.

T-SUB-04: Subtitles that are simply the author's name repeated are removed.

T-SUB-05: Volume and part designations in titles are governed by T-SER-01 —
           retain and standardize them. Do not remove volume/part numbers.

T-SUB-06: Use a colon (not em-dash, not semicolon) to separate title and
           subtitle in the cleaned version, with a single space on each side.

T-SUB-07: OMNIBUS / ANTHOLOGY TITLES WITH SLASH-SEPARATED WORKS — do NOT
           strip any of the individual work titles. When a title lists multiple
           collected works separated by " / " (or " / "), every slash-separated
           segment is part of the real title and must be kept intact.
           This applies especially to Library of America (LOA) volumes and
           similar collected-works editions.
           EXAMPLE title field:
             "James Agee: Let Us Now Praise Famous Men / A Death in the Family
              / Shorter Fiction (LOA #159)"
           WRONG: strip everything after the first slash, leaving only the first
                  work → "Let Us Now Praise Famous Men"
           RIGHT: keep all slash-separated works; remove only the series marker
                  per T-SER-02 → "Let Us Now Praise Famous Men / A Death in the
                  Family / Shorter Fiction"
           If an author name appears before the colon in such a title (e.g.
           "James Agee: …"), remove just that "Author: " prefix and keep the
           slash-separated works as the title.


---
## SECTION T-SER — Title: Series Information
---

T-SER-01: RETAIN volume and part numbers in titles — do not remove them.
           Standardize their format to ", Volume N" or ", Part N" at the end
           of the title, after any subtitle:
             "(Volume 2 of 3)"   → ", Volume 2"
             "(Volume 1)"        → ", Volume 1"
             "- Volume 1"        → ", Volume 1"
             "Vol. 2"            → ", Volume 2"
             "Volume 2 of 3"     → ", Volume 2"
           Use "high" confidence for mechanical format standardization.

T-SER-02: Series identifiers in parentheses or brackets containing a series
           name AND a book/volume number must be removed ENTIRELY — including
           the number. Do NOT retain the number or convert it to "Volume N".
           The whole parenthetical is gone; nothing replaces it.
           A "series-name parenthetical" is any parenthetical that contains:
             • any series name — short or long, one word or many
               (e.g. "Dune", "The Way", "Kithamar Trilogy", "Omega War")
             • followed by "Book N", "#N", or "Volume N"
           The series name does NOT need to be multi-word. Even a single word
           or short article+word ("The Way") qualifies if followed by Book N.
           ALL of the following patterns must be removed entirely:
             "(Jao Empire Book 3)"        → remove
             "(The Omega War Book 11)"    → remove
             "(The Neapolitan Novels #2)" → remove
             "[A Song of Ice and Fire, Book 1]" → remove
             "(Kithamar Trilogy #1)"      → remove
             "(The Way Book 1)"           → remove
             "(Dune Book 2)"              → remove
           WRONG: "The Span of Empire (Jao Empire Book 3)" → "The Span of Empire, Volume 3"
           RIGHT: "The Span of Empire (Jao Empire Book 3)" → "The Span of Empire"
           WRONG: "Sons of the Lion (The Omega War Book 11)" → "Sons of the Lion, Volume 11"
           RIGHT: "Sons of the Lion (The Omega War Book 11)" → "Sons of the Lion"
           WRONG: "Age of Ash (Kithamar Trilogy #1)" → "Age of Ash, Volume 1"
           RIGHT: "Age of Ash (Kithamar Trilogy #1)" → "Age of Ash"
           WRONG: "Eon (The Way Book 1)" → "Eon"  [leaving unchanged is also wrong]
           RIGHT: "Eon (The Way Book 1)" → "Eon"
           NOTE: leaving a series parenthetical unchanged is NOT correct —
           it must always be removed, even if the series name is short.
           The "#1" or "Book 1" inside the parenthetical is the series book
           position — it is NOT the same as a standalone volume number.
           Do NOT convert it to ", Volume 1". Remove the entire parenthetical.
           NOTE: T-SER-01 applies only to standalone volume numbers that are
           NOT inside a series-name parenthetical (e.g. "Title, Volume 2" or
           "Title (Volume 2)" with no series name present).

T-SER-03: Do not add series information that is not already present in
           the title field. If series data appears only in the Calibre
           series field, leave the title as-is.


---
## SECTION T-FMT — Title: Formatting & Punctuation
---

T-FMT-01: Normalize multiple consecutive spaces to a single space.

T-FMT-02: Remove leading and trailing whitespace from the title.

T-FMT-03: Remove trailing punctuation that is not part of the title:
           trailing commas, trailing semicolons, trailing periods
           (UNLESS the title ends in an abbreviation or ellipsis intentionally).

T-FMT-04: Normalize double punctuation:
             "!!" → "!"
             "??" → "?"
             ".." → "." (unless an intentional ellipsis)
             "..." is an acceptable ellipsis — leave as-is.

T-FMT-05: Do not change ampersand (&) to "and" or vice versa — follow the
           published title exactly in this respect.

T-FMT-06: Remove stray markdown or formatting characters that appear in the
           title field: asterisks (*), underscores (_), hash symbols (#),
           pipe characters (|).

T-FMT-07: Remove trademark (™) and registered (®) symbols.

T-FMT-08: Remove copyright symbols (©).

T-FMT-09: Convert all dash variants to a plain hyphen-minus (-).
           Em-dashes (—), en-dashes (–), and any other dash characters
           should become a simple hyphen. Apply to all occurrences in the
           title including between words and in date ranges.
           NOTE: the code will also enforce this automatically after your
           response, so focus on correctness rather than dash characters.
           EXCEPTION: if an em-dash is functioning as a subtitle separator
           (e.g. "Title — Subtitle"), apply T-SUB-06 first and convert it
           to a colon instead.

T-FMT-10: Do NOT add or remove commas before years or date ranges.
           Leave whatever punctuation is already there exactly as-is.
           WRONG (removing a comma that exists): "King Years 1963-65"
             when original was "King Years, 1963-65"
           WRONG (adding a comma that doesn't exist): "King Years, 1954-63"
             when original was "King Years 1954-63"
           RIGHT: leave the comma (or its absence) exactly as found.

T-FMT-11: If the title field contains a filing form with the article moved
           to the end (e.g. "Road, The" or "Remains of the Day, The"),
           restore it to normal order: "The Road", "The Remains of the Day".

T-FMT-12: Remove ISBN numbers, barcode strings, or other numeric identifiers
           that have been incorrectly placed in the title field.

T-FMT-13: Remove language identifiers appended to titles:
             "(In French)"
             "[Spanish]"
             "(English translation)"

T-FMT-14: Remove reading group guide references:
             "(With Reading Group Guide)"
             "(Includes Reader's Guide)"

T-FMT-15: If a title appears to be a duplicate with minor variation
           (e.g. same title appears twice with slightly different formatting),
           flag it with "low" confidence and note the possible duplicate
           rather than attempting to fix it.


---
## SECTION A-ORD — Author: Name Format & Order
---

A-ORD-01: Author names must be in "First Last" order.
           Invert any name stored as "Last, First":
             "Mantel, Hilary" → "Hilary Mantel"
             "García Márquez, Gabriel" → "Gabriel García Márquez"

A-ORD-02: When inverting "Last, First" names, be careful with compound
           surnames. "Branch, Taylor" → "Taylor Branch" (simple).
           "García Márquez, Gabriel" → "Gabriel García Márquez" (compound).

A-ORD-03: If a name has no comma and is already in "First Last" order,
           leave the order unchanged.

A-ORD-04: Preserve middle names and middle initials exactly as stored:
             "William H. Gass" stays "William H. Gass"
             "T. Coraghessan Boyle" stays "T. Coraghessan Boyle"

A-ORD-05: Preserve name suffixes: Jr., Sr., II, III, IV.
           Place them at the end: "John Updike Jr."


---
## SECTION A-MUL — Author: Multiple Authors
---

A-MUL-01: When multiple authors are present, separate them with " & "
           (ampersand with a space on each side).

A-MUL-02: Replace all other separators with " & ":
             "and" → "&"         (e.g. "Smith and Jones" → "Smith & Jones")
             ";" → "&"
             "/" → "&"
             "|" → "&"
             "," between full names → "&"

A-MUL-03: Do NOT use "&" inside a single person's name.
           "Ursula K. Le Guin" is one author — no ampersand.

A-MUL-04: Each individual author's name is still formatted First Last
           after the separators are normalized.

A-MUL-05: If there are more than three authors and the field contains
           "et al.", flag with "low" confidence — do not attempt to
           expand "et al." and do not remove it without confirmation.


---
## SECTION A-ROL — Author: Roles, Honorifics & Annotations
---

A-ROL-01: Remove role labels appended to author names, but keep the name:
             "Hilary Mantel (ed.)" → "Hilary Mantel"
             "John Smith (editor)" → "John Smith"
             "Jane Doe (trans.)" → "Jane Doe"
             "Jane Doe (translator)" → "Jane Doe"
             "Bob Brown (illus.)" → "Bob Brown"
             "Bob Brown (illustrator)" → "Bob Brown"
             "Alice Green (comp.)" → "Alice Green"
             "Alice Green (compiler)" → "Alice Green"
             "Alice Green (compiled by)" → "Alice Green"

A-ROL-02: Remove "Edited by" prefix: "Edited by Hilary Mantel" → "Hilary Mantel"

A-ROL-03: Remove "Translated by" prefix: "Translated by Gregory Rabassa" → "Gregory Rabassa"

A-ROL-04: Remove "Introduction by [Name]" entirely — the introducer is not a
           primary author and should not appear in the authors field.

A-ROL-05: Remove "Foreword by [Name]" and "Afterword by [Name]" entirely.

A-ROL-06: Remove "Preface by [Name]" entirely.

A-ROL-07: Remove honorific titles from the beginning of names:
             "Dr. " → remove
             "Prof. " → remove
             "Sir " → remove
             "Dame " → remove
             "Lord " → remove
             "Lady " → remove
           EXCEPTION: if the honorific is so closely associated with the
           person's public identity that omitting it would cause confusion,
           use "medium" confidence and note the case.

A-ROL-08: Remove birth/death years appended to author names:
             "Gabriel García Márquez (1927-2014)" → "Gabriel García Márquez"
             "Chinua Achebe (b. 1930)" → "Chinua Achebe"

A-ROL-09: Remove nationality or occupation annotations:
             "Toni Morrison (American)" → "Toni Morrison"
             "Kazuo Ishiguro (novelist)" → "Kazuo Ishiguro"

A-ROL-10: When a book has BOTH personal author(s) AND corporate/institutional
           co-author(s), remove the corporate co-authors and keep only the
           personal authors. Corporate bodies as co-authors add little value
           and cause formatting problems.
           EXAMPLE: "Peter Davies & United Methodist Church (U.S.) Board of
           Church & Society" → "Peter Davies"
           EXCEPTION: If ALL listed authors are corporate/institutional with
           no personal author present (e.g. a government report, a commission
           publication, an anthology with no named editor), retain the
           corporate author as-is.

A-ROL-11: When a corporate/institutional author name contains "&", replace
           "&" with "and" to prevent the library software from incorrectly
           splitting the name into multiple authors.
           EXAMPLE: "National Board of Church & Society" →
                    "National Board of Church and Society"


---
## SECTION A-SPE — Author: Special & Edge Cases
---

A-SPE-01: Single-name authors (classical or pen names) — leave as a single name:
             "Homer", "Virgil", "Voltaire", "Molière", "Saki"
           Do not attempt to add a last name.

A-SPE-02: Authors known by initials — preserve the initials exactly:
             "J.K. Rowling", "P.D. James", "E.M. Forster", "C.S. Lewis"
           Do not expand initials to full first names.

A-SPE-03: Authors with "de", "van", "von", "du", "della", "di" particles:
           - Lowercase the particle in the middle of the full name:
               "Gabriel de la Mora", "Ludwig van Beethoven"
           - If only the surname is present, capitalise the particle:
               "De La Mora", "Van Beethoven"

A-SPE-04: Celtic prefixes: "Mac", "Mc", "O'" — preserve exactly as stored.
           "Cormac McCarthy" stays "Cormac McCarthy".
           Do not normalise "Mc" to "Mac" or vice versa.

A-SPE-05: Hyphenated surnames — preserve the hyphen:
             "Jean-Paul Sartre", "Chimamanda Ngozi Adichie"

A-SPE-06: Diacritics and accented characters — return them exactly as you
           would normally write them. The system will automatically convert
           all accented characters to plain ASCII after your response
           (e.g. é→e, ä→a, ß→ss, García→Garcia). You do not need to
           handle this conversion yourself — focus on correctness of the
           name or title, not the character encoding.

A-SPE-07: Corporate, institutional, or collective authors — leave exactly
           as stored. Do not attempt to reformat them as personal names.
           Examples: "Anonymous", "Various Authors", "The Paris Review Editors"
           IMPORTANT: If a corporate author name contains "&", do NOT treat
           it as an author separator. The entire name including "&" is one
           single author entry. Indicators of a corporate author include:
           Church, Board, University, Institute, Foundation, Society,
           Association, Committee, Department, Council, Organization,
           Ministry, Bureau, Office, Agency, Trust, Commission, Centre.
           Example: "United Methodist Church (U.S.) Board of Church & Society"
           is ONE author — do not split on the "&".

A-SPE-08: Author names that are pen names — treat the pen name as a full,
           correct author name. Do not replace pen names with legal names
           (e.g. keep "George Orwell", not "Eric Arthur Blair").

A-SPE-09: Authors where first name is an initial and last name is a full name
           (e.g. "J. M. Coetzee") — preserve spacing between initials.
           "J.M. Coetzee" and "J. M. Coetzee" are both acceptable;
           do not change one to the other unless clearly inconsistent
           within the same author's other entries.

A-SPE-10: "Anonymous" — leave as-is. Do not attempt to identify the author.


---
## SECTION A-CLN — Author: Cleanup & Normalization
---

A-CLN-01: Remove leading and trailing whitespace from author names.

A-CLN-02: Normalize multiple consecutive spaces within a name to a single space.

A-CLN-03: Author names in ALL CAPS — convert to proper name case:
             "HILARY MANTEL" → "Hilary Mantel"
           Apply A-SPE rules for particles and prefixes after conversion.

A-CLN-04: Author names in all lowercase (and not a stylistic choice) —
           convert to proper name case: "hilary mantel" → "Hilary Mantel"

A-CLN-05: Remove stray punctuation at the start or end of an author name:
           leading/trailing commas, periods (unless part of initials),
           semicolons, quotation marks.

A-CLN-06: If the author field contains what appears to be a title or ISBN
           rather than a name, flag it with "low" confidence — do not guess.

A-CLN-07: If the author field contains an email address or URL, remove it.


---
## SECTION GEN — General Behaviour
---

GEN-01: When no change is needed, return the original value unchanged and
        set confidence to "high". Note: "No changes needed."

GEN-02: When a rule clearly and unambiguously applies, use "high" confidence.

GEN-03: When applying a rule requires a judgment call or interpretation,
        use "medium" confidence.

GEN-04: When you are uncertain whether a change is correct, use "low"
        confidence. It is better to flag something for human review
        than to make a wrong change silently.

GEN-05: Never invent or fabricate information. If you do not know the correct
        form of an author's name or a book's title, leave it unchanged
        and note your uncertainty.

GEN-06: Treat each book independently. Do not infer corrections for one book
        based on patterns in other books in the same batch.

GEN-07: The "notes" field should briefly explain what was changed and why,
        or confirm "No changes needed." Keep notes to one sentence.

GEN-08: Return results in the same order as the input. Do not reorder books.

GEN-09: The output must be a valid JSON array. No markdown fences, no
        commentary outside the array, no trailing commas.

GEN-10: If you notice that the title and author fields appear to be swapped
        (e.g. the title field contains a person's name, or the author field
        contains what looks like a book title), suggest the corrected values
        using your knowledge of the book. Use "low" confidence and note
        "Possible title/author swap detected - please verify."
        If you recognise the book, provide the correct title and author.
        If you do not recognise it, flag the swap but do not guess.
        EXAMPLE: title="Octavia Butler - Parable 02",
                 author="Parable of the Talents"
        SUGGESTION: title="Parable of the Talents", author="Octavia Butler"
        NOTE: "Possible title/author swap detected - please verify."
