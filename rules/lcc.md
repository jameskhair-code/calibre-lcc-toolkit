# LCC Enrichment Rules
# Literary Awards & Nominees Collection — MQG-03
#
# Rules are grouped by category and numbered for reference.
# Add, remove, or edit rules here — no code changes required.
# Confidence guide: apply "high" only when evidence is catalog-confirmed.


---
## SECTION SCOPE — What This Task Is
---

SCOPE-01: For each book, you propose four LCC metadata values:
            - lcc                    the LCC call number
            - lcc_primary_class      controlled drop-down (21 values)
            - lcc_secondary_class    controlled drop-down (~232 values)
            - lcc_class_path         narrative breadcrumb (free text)
           Plus: confidence, source, and notes.

SCOPE-02: This is NOT original professional cataloging. You are building local
           metadata for a personal library by leveraging existing catalog
           evidence (Library of Congress, WorldCat, university libraries) and
           the public LCC schedule structure.

SCOPE-03: Evidence beats invention. A catalog-confirmed value for the wrong
           edition is usually better than a guess. A schedule-derived value
           based on subject knowledge is acceptable as a fallback, but must be
           flagged with lower confidence.

SCOPE-04: Do not force precision. If you cannot support a full Cutter/year
           extension from evidence, return the most specific portion you can
           support (e.g. just the class+number, or just the class letters)
           and use "low" confidence with a note explaining the limit.


---
## SECTION SRC — Evidence & Source Quality
---

SRC-01: Preferred evidence order, strongest first:
          1. Library of Congress catalog record, same edition / ISBN.
          2. WorldCat / OCLC consensus across multiple library records.
          3. University or national library catalog record matching the work.
          4. Publisher CIP-style metadata.
          5. Schedule-derived classification from the LCC outline + subject.

SRC-02: When multiple catalog records disagree:
          - Prefer the Library of Congress value.
          - If LC is silent, prefer the value that appears most consistently
            across reputable libraries.
          - If conflict is genuine and unresolvable, return the safer
            (less specific) value and flag "low" confidence for review.

SRC-03: Edition matching factors, in priority order:
          ISBN > Author + Title + Year > Author + Title > Title alone.
          Reprints and public-domain editions often share LCC with the
          original cataloged edition — this is usually acceptable but should
          be noted in the source field when the ISBN does not match.

SRC-04: Dissertations vs. later published books are separate bibliographic
          objects. Do not silently reuse a dissertation's LCC for the
          commercial book or vice versa.

SRC-05: The "source" field should be a short phrase describing the strongest
          piece of evidence used. Examples:
            "Library of Congress catalog, exact ISBN match"
            "WorldCat consensus across 4+ library records"
            "Harvard catalog, matching edition"
            "LCC schedule, derived from subject (no catalog record found)"


---
## SECTION LCC — The Call Number Field
---

LCC-01: The lcc field holds a single LCC call number in canonical spaced form.
          Examples:
            "DK189 .W67 2003"
            "BM197.5 .K64 2003"
            "PS3563.O8749 B45 1987"

LCC-02: Format conventions:
          - Class letters immediately followed by class number — no space.
            RIGHT: "DK189"     WRONG: "DK 189"
          - One space before the Cutter dot.
            RIGHT: "DK189 .W67"   WRONG: "DK189.W67"
          - One space before any subsequent Cutter or year.
            RIGHT: "DK189 .W67 2003"
          - Decimal class numbers: keep the dot, no space.
            RIGHT: "BM197.5 .K64"
          - Letters are uppercase. Cutter letters are uppercase.

LCC-03: If the evidence supports only a partial call number, return what is
          supported. Do not fabricate Cutters or years.
            "DK189"           — class+number only, no Cutter found
            "DK189 .W67"      — class+number+Cutter, no year found
            "DK"              — only the subclass letters can be supported
          Use "low" confidence for partial values.

LCC-04: When the call number you find uses period-Cutter without a leading
          space (e.g. "DK189.W67"), normalise it to spaced form
          ("DK189 .W67") to match LC convention.

LCC-05: If no LCC value can be reasonably derived or confirmed, return an
          empty string for lcc and flag confidence "low" with a note
          explaining what was searched and what was missing.


---
## SECTION PRI — LCC Primary Class (Drop-down)
---

PRI-01: lcc_primary_class is a controlled drop-down. You MUST return one
          of the 21 canonical values listed in PRI-04 exactly as written.
          Any deviation (extra spaces, different punctuation, abbreviation)
          will be rejected by validation.

PRI-02: Derive the primary class from the leading letter of the LCC call
          number. The mapping is mechanical:

            A → A - General Works
            B → B - Philosophy & Psychology & Religion
            C → C - Auxiliary Sciences of History
            D → D - World History & Area Studies
            E → E - History of the Americas
            F → F - History of the Americas
            G → G - Geography & Anthropology & Recreation
            H → H - Social Sciences
            J → J - Political Science
            K → K - Law
            L → L - Education
            M → M - Music
            N → N - Fine Arts
            P → P - Language & Literature
            Q → Q - Science
            R → R - Medicine
            S → S - Agriculture
            T → T - Technology
            U → U - Military Science
            V → V - Naval Science
            Z → Z - Bibliography & Library Science

PRI-03: E and F both map to "E - History of the Americas" / "F - History of
          the Americas". Use the letter that matches the actual call number.
          (E covers American history generally; F covers local/regional.)

PRI-04: There are 21 valid lcc_primary_class values. The complete list is in
          PRI-02 above. No other strings are valid.

PRI-05: If lcc is empty, lcc_primary_class should still be your best subject-
          based proposal — pick the class whose scope best fits the book's
          subject and flag "low" confidence.


---
## SECTION SEC — LCC Secondary Class (Drop-down)
---

SEC-01: lcc_secondary_class is a controlled drop-down. You MUST return one
          of the canonical values listed in SEC-05 exactly as written.

SEC-02: Derive the secondary class from the subclass letters of the LCC call
          number (the letters immediately preceding the first digit).
          Examples:
            "DK189 .W67 2003"      → subclass "DK"  → "DK - Russia & Soviet Union & Former Republics"
            "BM197.5 .K64 2003"    → subclass "BM"  → "BM - Judaism"
            "PS3563.O8749 B45"     → subclass "PS"  → "PS - American Literature"
            "HD8390.B73 K63 1990"  → subclass "HD"  → "HD - Industries & Land Use & Labor"

SEC-03: Special cases — range-coded secondaries for E and F:
            E11-143      → "E11-143 - Americas: Pre-Colonial & Colonial"
            E151-909     → "E151-909 - United States: History"
            F1-975       → "F1-975 - United States: Local & Regional History"
            F1001-1145   → "F1001-1145 - Canada & British America"
            F1170        → "F1170 - French America"
            F1201-3799   → "F1201-3799 - Latin America & Caribbean"
          When the lcc number falls in one of these ranges, prefer the range-
          coded secondary over the bare "E" or "F" value.

SEC-04: Special cases — combined-range secondaries:
            KD or KDK    → "KD-KDK - Law: United Kingdom & Ireland"
            KG through KH  → "KG-KH - Law: Latin America & South America"
            KJ through KKZ → "KJ-KKZ - Law: Europe"
            KL through KWX → "KL-KWX - Law: Asia & Eurasia & Africa & Pacific"
          When the subclass letters fall in one of these combined ranges,
          use the combined-range secondary.

SEC-05: Canonical secondary-class list, organised by primary class.
          Use the EXACT string on the right of the arrow.

          A — General Works
            A     → "A - General Works"
            AC    → "AC - Collections & Series & Collected Works"
            AE    → "AE - Encyclopedias"
            AG    → "AG - Dictionaries and Other General Reference Works"
            AI    → "AI - Indexes"
            AM    → "AM - Museums & Collecting"
            AN    → "AN - Newspapers"
            AP    → "AP - Periodicals"
            AS    → "AS - Academies and Learned Societies"
            AY    → "AY - Yearbooks & Almanacs & Directories"
            AZ    → "AZ - History of Scholarship & The Humanities"

          B — Philosophy, Psychology & Religion
            B     → "B - Philosophy General"
            BC    → "BC - Logic"
            BD    → "BD - Speculative Philosophy"
            BF    → "BF - Psychology"
            BH    → "BH - Aesthetics"
            BJ    → "BJ - Ethics"
            BL    → "BL - Religions & Mythology & Rationalism"
            BM    → "BM - Judaism"
            BP    → "BP - Islam & Bahai Faith & Theosophy"
            BQ    → "BQ - Buddhism"
            BR    → "BR - Christianity"
            BS    → "BS - The Bible"
            BT    → "BT - Doctrinal Theology"
            BV    → "BV - Practical Theology"
            BX    → "BX - Christian Denominations"

          C — Auxiliary Sciences of History
            C     → "C - Auxiliary Sciences of History General"
            CB    → "CB - History of Civilization"
            CC    → "CC - Archaeology"
            CD    → "CD - Diplomatics & Archives & Seals"
            CE    → "CE - Technical Chronology & Calendar"
            CJ    → "CJ - Numismatics"
            CN    → "CN - Inscriptions & Epigraphy"
            CR    → "CR - Heraldry"
            CS    → "CS - Genealogy"
            CT    → "CT - Biography"

          D — World History & Area Studies
            D     → "D - History General"
            DA    → "DA - Great Britain"
            DAW   → "DAW - Central Europe"
            DB    → "DB - Austria & Hungary & Central Europe"
            DC    → "DC - France & Andorra & Monaco"
            DD    → "DD - Germany"
            DE    → "DE - Greco-Roman World"
            DF    → "DF - Greece"
            DG    → "DG - Italy & Malta"
            DH    → "DH - Low Countries & Benelux"
            DJ    → "DJ - Netherlands"
            DJK   → "DJK - Eastern Europe General"
            DK    → "DK - Russia & Soviet Union & Former Republics"
            DL    → "DL - Northern Europe & Scandinavia"
            DP    → "DP - Spain & Portugal"
            DQ    → "DQ - Switzerland"
            DR    → "DR - Balkan Peninsula"
            DS    → "DS - Asia"
            DT    → "DT - Africa"
            DU    → "DU - Oceania & Pacific"
            DX    → "DX - Romanies"

          E — History of the Americas (general)
            E         → "E - Americas: General History"
            E11-143   → "E11-143 - Americas: Pre-Colonial & Colonial"
            E151-909  → "E151-909 - United States: History"

          F — History of the Americas (local)
            F             → "F - Americas: Local History"
            F1-975        → "F1-975 - United States: Local & Regional History"
            F1001-1145    → "F1001-1145 - Canada & British America"
            F1170         → "F1170 - French America"
            F1201-3799    → "F1201-3799 - Latin America & Caribbean"

          G — Geography, Anthropology & Recreation
            G     → "G - Geography: General & Atlases & Maps"
            GA    → "GA - Mathematical Geography & Cartography"
            GB    → "GB - Physical Geography"
            GC    → "GC - Oceanography"
            GE    → "GE - Environmental Sciences"
            GF    → "GF - Human Ecology & Anthropogeography"
            GN    → "GN - Anthropology"
            GR    → "GR - Folklore"
            GT    → "GT - Manners & Customs"
            GV    → "GV - Recreation & Leisure"

          H — Social Sciences
            H     → "H - Social Sciences General"
            HA    → "HA - Statistics"
            HB    → "HB - Economic Theory & Demography"
            HC    → "HC - Economic History and Conditions"
            HD    → "HD - Industries & Land Use & Labor"
            HE    → "HE - Transportation & Communications"
            HF    → "HF - Commerce"
            HG    → "HG - Finance"
            HJ    → "HJ - Public Finance"
            HM    → "HM - Sociology: General"
            HN    → "HN - Social History & Social Reform"
            HQ    → "HQ - Family & Marriage & Women"
            HS    → "HS - Societies & Organizations"
            HT    → "HT - Communities & Classes & Races"
            HV    → "HV - Criminology & Social Welfare"
            HX    → "HX - Socialism & Communism & Anarchism"

          J — Political Science
            J     → "J - Legislative & Executive Papers"
            JA    → "JA - Political Science General"
            JC    → "JC - Political Theory"
            JF    → "JF - Political Institutions & Administration"
            JJ    → "JJ - Political Administration: North America"
            JK    → "JK - Political Administration: United States"
            JL    → "JL - Political Administration: Canada & Latin America"
            JN    → "JN - Political Administration: Europe"
            JQ    → "JQ - Political Administration: Asia & Africa & Pacific"
            JS    → "JS - Local & Municipal Government"
            JV    → "JV - Colonization & Immigration"
            JZ    → "JZ - International Relations"

          K — Law
            K           → "K - Law: General & Jurisprudence"
            KB          → "KB - Religious Law: General"
            KBM         → "KBM - Jewish Law"
            KBP         → "KBP - Islamic Law"
            KBR         → "KBR - History of Canon Law"
            KBU         → "KBU - Catholic Church Law & The Holy See"
            KD / KDK    → "KD-KDK - Law: United Kingdom & Ireland"
            KDZ         → "KDZ - Law: North America"
            KE          → "KE - Law: Canada"
            KF          → "KF - Law: United States"
            KG-KH       → "KG-KH - Law: Latin America & South America"
            KJ-KKZ      → "KJ-KKZ - Law: Europe"
            KL-KWX      → "KL-KWX - Law: Asia & Eurasia & Africa & Pacific"
            KZ          → "KZ - Law of Nations"

          L — Education
            L     → "L - Education General"
            LA    → "LA - History of Education"
            LB    → "LB - Theory & Practice of Education"
            LC    → "LC - Special Aspects of Education"
            LD    → "LD - Educational Institutions: United States"
            LE    → "LE - Educational Institutions: Americas (excl. US)"
            LF    → "LF - Educational Institutions: Europe"
            LG    → "LG - Educational Institutions: Asia & Africa & Pacific"
            LH    → "LH - College & School Publications"
            LJ    → "LJ - Student Organizations: United States"
            LT    → "LT - Textbooks"

          M — Music
            M     → "M - Music"
            ML    → "ML - Literature on Music"
            MT    → "MT - Music Instruction & Study"

          N — Fine Arts
            N     → "N - Visual Arts"
            NA    → "NA - Architecture"
            NB    → "NB - Sculpture"
            NC    → "NC - Drawing & Design & Illustration"
            ND    → "ND - Painting"
            NE    → "NE - Print Media"
            NK    → "NK - Decorative Arts"
            NX    → "NX - Arts: General"

          P — Language & Literature
            P     → "P - Philology & Linguistics"
            PA    → "PA - Classical Languages & Literature"
            PB    → "PB - Modern & Celtic Languages"
            PC    → "PC - Romanic Languages"
            PD    → "PD - Germanic & Scandinavian Languages"
            PE    → "PE - English Language"
            PF    → "PF - West Germanic Languages"
            PG    → "PG - Slavic & Baltic Languages"
            PH    → "PH - Uralic & Basque Languages"
            PJ    → "PJ - Oriental Languages & Literature"
            PK    → "PK - Indo-Iranian Languages & Literature"
            PL    → "PL - Languages: East Asia & Africa & Oceania"
            PM    → "PM - Indigenous & Constructed Languages"
            PN    → "PN - Literature General"
            PQ    → "PQ - Romance-Language Literatures"
            PR    → "PR - English Literature"
            PS    → "PS - American Literature"
            PT    → "PT - Germanic & Scandinavian Literatures"
            PZ    → "PZ - Fiction & Juvenile Literature"

          Q — Science
            Q     → "Q - Science General"
            QA    → "QA - Mathematics"
            QB    → "QB - Astronomy"
            QC    → "QC - Physics"
            QD    → "QD - Chemistry"
            QE    → "QE - Geology"
            QH    → "QH - Natural History & Biology"
            QK    → "QK - Botany"
            QL    → "QL - Zoology"
            QM    → "QM - Human Anatomy"
            QP    → "QP - Physiology"
            QR    → "QR - Microbiology"

          R — Medicine
            R     → "R - Medicine General"
            RA    → "RA - Public Health & Medicine"
            RB    → "RB - Pathology"
            RC    → "RC - Internal Medicine"
            RD    → "RD - Surgery"
            RE    → "RE - Ophthalmology"
            RF    → "RF - Otorhinolaryngology"
            RG    → "RG - Gynecology & Obstetrics"
            RJ    → "RJ - Pediatrics"
            RK    → "RK - Dentistry"
            RL    → "RL - Dermatology"
            RM    → "RM - Therapeutics & Pharmacology"
            RS    → "RS - Pharmacy & Materia Medica"
            RT    → "RT - Nursing"
            RV    → "RV - Botanical & Alternative Medicine"
            RX    → "RX - Homeopathy"
            RZ    → "RZ - Other Medical Systems"

          S — Agriculture
            S     → "S - Agriculture General"
            SB    → "SB - Plant Culture"
            SD    → "SD - Forestry"
            SF    → "SF - Animal Husbandry & Culture"
            SH    → "SH - Aquaculture & Fisheries & Angling"
            SK    → "SK - Hunting & Field Sports"

          T — Technology
            T     → "T - Technology General"
            TA    → "TA - Engineering: General & Civil"
            TC    → "TC - Hydraulic & Ocean Engineering"
            TD    → "TD - Environmental & Sanitary Engineering"
            TE    → "TE - Highway Engineering & Roads"
            TF    → "TF - Railroad Engineering and Operation"
            TG    → "TG - Bridge Engineering"
            TH    → "TH - Building Construction"
            TJ    → "TJ - Mechanical Engineering and Machinery"
            TK    → "TK - Electrical & Electronics & Nuclear Engineering"
            TL    → "TL - Vehicles & Aviation & Space"
            TN    → "TN - Mining & Metallurgy"
            TP    → "TP - Chemical Technology"
            TR    → "TR - Photography"
            TS    → "TS - Manufactures"
            TT    → "TT - Handicrafts & Arts and Crafts"
            TX    → "TX - Home Economics"

          U — Military Science
            U     → "U - Military Science General"
            UA    → "UA - Armies & Military Organization"
            UB    → "UB - Military Administration"
            UC    → "UC - Military Maintenance & Transport"
            UD    → "UD - Infantry"
            UE    → "UE - Cavalry & Armor"
            UF    → "UF - Artillery"
            UG    → "UG - Military Engineering & Air Forces"
            UH    → "UH - Other Military Services"

          V — Naval Science
            V     → "V - Naval Science General"
            VA    → "VA - Navies & Naval Organization"
            VB    → "VB - Naval Administration"
            VC    → "VC - Naval Maintenance"
            VD    → "VD - Naval Seamen"
            VE    → "VE - Marines"
            VF    → "VF - Naval Ordnance"
            VG    → "VG - Minor Naval Services"
            VK    → "VK - Navigation & Merchant Marine"
            VM    → "VM - Naval Architecture & Shipbuilding"

          Z — Bibliography & Library Science
            Z     → "Z - Books & Libraries & Bibliography"
            ZA    → "ZA - Information Resources General"

SEC-06: If lcc is empty, lcc_secondary_class should still be your best
          subject-based proposal. Pick the subclass whose scope best fits
          the book's actual subject and flag "low" confidence.

SEC-07: When only a single letter (e.g. "B") is supportable, use the
          general-form secondary value (e.g. "B - Philosophy General"),
          not a deeper guess.


---
## SECTION PATH — LCC Subject Descriptor
---

PATH-01: lcc_class_path is a subject descriptor — 3 to 5 short noun-based
           phrases (2–4 words each) that name the specific intellectual
           territory of this book. The goal: a reader scanning these phrases
           should immediately understand what this book is actually about at
           its most specific level.

PATH-02: Do NOT repeat what the primary or secondary class already
           communicates. Those fields cover the broad LCC category (e.g.
           "Military Science", "Home Economics"). The descriptor opens where
           those leave off and goes deeper into the book's actual subject.

PATH-03: Canonical format:
           "<Phrase one> · <Phrase two> · <Phrase three>"
           Separator is " · " (space, middle dot U+00B7, space).
           3 phrases minimum, 5 maximum.
           Each phrase 2–4 words, title case, no trailing punctuation.

PATH-04: Include time period and geography ONLY when they add information
           the LCC secondary class does not already communicate AND when they
           are genuinely distinctive to this book's subject.
           Include:
             - Period when it is the subject ("Cold War · 1945–1990")
             - Geography when it is the subject and not implied by the
               secondary class ("Early modern Spain · Atlantic empire")
           Omit:
             - Geography already implied by the secondary class
               (DK already means Russia — don't add "Russia" as a phrase)
             - Period obvious from the call number year alone
             - Contemporary/present-day books where period adds no meaning

PATH-05: Write noun-based phrases as you would if they might become subject
           tags. Prefer specific, concrete terms over abstract or generic ones.
           Good:  "Fast food franchising"  "Strategic deterrence"  "Print culture"
           Avoid: "Historical analysis"  "Cultural context"  "Various topics"

PATH-06: Examples spanning different classes:

           Book:  "Danger and Survival: Choices About the Bomb in the First Fifty Years"
           LCC:   "UA23 .B7862 1990"  Sec: "UA - Armies & Military Organization"
           Desc:  "Nuclear policy · Strategic deterrence · Cold War decision-making · 1945–1990"

           Book:  "Franchise: The Golden Arches in Black America"
           LCC:   "TX945.5.M33 C43 2020"  Sec: "TX - Home Economics"
           Desc:  "Fast food franchising · McDonald's Corporation · Race and capitalism · Black economic history"

           Book:  "Six Galleons for the King of Spain"
           LCC:   "VA583 .P48 1986"  Sec: "VA - Navies & Naval Organization"
           Desc:  "Spanish naval logistics · Atlantic empire · Early modern defense · 17th-century galleons"

           Book:  "The Nature of the Book: Print and Knowledge in the Making"
           LCC:   "Z124 .J64 1998"  Sec: "Z - Books & Libraries & Bibliography"
           Desc:  "Print culture · Knowledge production · Early modern England · Authorship and the press"

           Book:  "Sailing School: Navigating Science and Skill, 1550–1800"
           LCC:   "VK455 .S36 2019"  Sec: "VK - Navigation & Merchant Marine"
           Desc:  "Nautical instruction · Navigation science · Early modern Europe · 1550–1800"

           Book:  "Scenarios of Power: Myth and Ceremony in Russian Monarchy"
           LCC:   "DK189 .W67 2003"  Sec: "DK - Russia & Soviet Union & Former Republics"
           Desc:  "Imperial monarchy · Court ceremony · Political myth · Romanov dynasty"
           (geography omitted — DK already implies Russia)

PATH-07: When lcc is empty, derive the descriptor from the best available
           subject evidence — title, author, known subject. Flag "low"
           confidence.

PATH-08: Do not use commas, semicolons, or " > " separators anywhere in the
           descriptor. The only separator is " · ". Do not use slashes within
           phrases.


---
## SECTION CONF — Confidence Levels
---

CONF-01: "high" — catalog-confirmed for the same edition.
           Strong typical signals:
             - ISBN match in Library of Congress catalog.
             - Same edition match in multiple reputable library catalogs.
             - All four output fields are well-supported by the source.

CONF-02: "medium" — catalog-consensus across editions or close-but-not-exact
           edition match. Examples:
             - Earlier or later edition of same work shows same LCC.
             - WorldCat shows consistent class across several library records.
             - Edition is a reprint, but original cataloging is clear.

CONF-03: "low" — schedule-derived, partial, ambiguous, or no catalog evidence.
           Examples:
             - No catalog record found; classification derived from subject.
             - Catalog records disagree.
             - Only the primary class letter is confidently supported.
             - Multidisciplinary work where multiple classes are plausible.
             - Title/author search returns nothing matching.

CONF-04: Use "low" liberally. A "low" record is auto-flagged for manual
           review — that is the correct outcome when evidence is weak.
           Do not inflate confidence to avoid the review flag.

CONF-05: The confidence applies to the full set of four LCC fields. If
           lcc is "low" but the primary/secondary are obvious from subject,
           use "low" for the whole record — the manual-review flag protects
           the call number, which is the field most likely to be wrong.


---
## SECTION GEN — Output Format & General Behaviour
---

GEN-01: Return one JSON object per book, in the same order as the input.
          The wrapping output must be a valid JSON array.

GEN-02: Required keys per book object:
          {
            "lcc": "DK189 .W67 2003",
            "lcc_primary_class": "D - World History & Area Studies",
            "lcc_secondary_class": "DK - Russia & Soviet Union & Former Republics",
            "lcc_class_path": "D. World History > DK. Russia & Soviet Union & Former Republics > Russia - History > Imperial Russia / Romanov Monarchy > Court Ceremony / Political Myth / Monarchical Representation",
            "confidence": "high",
            "source": "Library of Congress catalog, exact ISBN match",
            "notes": "LC record confirms class for this edition."
          }

GEN-03: Primary and secondary class strings MUST match the canonical values
          in PRI and SEC exactly. Any extra space, missing word, or
          punctuation variation will fail validation downstream.

GEN-04: No markdown fences. No commentary outside the JSON array. No
          trailing commas. No comments inside the JSON.

GEN-05: Treat each book independently. Do not infer classification for one
          book from patterns in other books in the same batch (different
          subject matter, even by the same author, can land in different
          classes).

GEN-06: Never invent a call number. If catalog evidence is missing, return
          empty lcc and a subject-derived primary/secondary/path with
          "low" confidence.

GEN-07: The notes field should be one short sentence describing the
          evidence basis or any concern. Keep it concise.

GEN-08: If the book identity itself is ambiguous (multiple works with the
          same title and author, dissertation vs. published book, etc.),
          flag "low" confidence and explain the ambiguity in notes.


---
## SECTION RISK — Known Risk Areas
---

RISK-01: Reprints with modern ISBNs may carry LCC of the original edition.
          Note this in the source field; "low" or "medium" confidence is
          appropriate depending on how stable the subject placement is.

RISK-02: Multidisciplinary works (history-of-science, religion-and-politics,
          biography-of-an-artist, etc.) often sit between two classes.
          Prefer the class supported by catalog consensus over your own
          intuition. Flag "low" if catalogs disagree.

RISK-03: Dissertations vs. trade books — treat them as different objects.

RISK-04: Public-domain reprints and "anniversary editions" often produce
          modern ISBNs that point at very old works. Use the LCC of the
          original work and note this in source.

RISK-05: Translated works — the LCC typically follows the original work's
          subject placement, not the translation. The PJ-PT literature
          subclasses are exceptions where the language of the work matters.


---
## SECTION RULE — Practical Rule
---

RULE-01: When in doubt:
            Do not force the metadata.
            Return a shorter, less specific value.
            Flag "low" confidence.
            The manual-review queue will catch it.
          Boring, conservative metadata is good metadata.
