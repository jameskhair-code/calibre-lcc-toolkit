# LCC Methodology

This document describes the methodology used to gather, evaluate, normalize, and apply Library of Congress Classification (LCC) metadata in the Calibre LCC Toolkit workflow.

The goal is not to perform original professional cataloging from scratch. The goal is to build high-quality local Calibre metadata by using catalog evidence, official LCC structure, controlled local dropdown values, and human review.

---

## Methodology Summary

The toolkit workflow separates LCC work into two different concerns:

1. **LCC enrichment** - researching or deriving the proposed LCC values.
2. **LCC application** - validating and safely writing approved values into Calibre.

The toolkit handles the second concern. ChatGPT/library research currently assists with the first.

```text
Export source TSV -> Enrich LCC values -> Prepare -> Validate -> Apply -> Verify
```

The enrichment step produces a completed import TSV. The toolkit then canonicalizes, dry-runs, applies, and verifies the import.

---

## Authoritative Reference Model

The Library of Congress Classification is the underlying classification system. The Library of Congress describes LCC as a system developed in the late nineteenth and early twentieth centuries to organize and arrange the Library's collections. The Library of Congress also publishes approved classification changes over time.

The current public reference sources used as anchors are:

- Library of Congress Classification and Shelflisting
- Library of Congress Classification Outline
- Library of Congress Classification PDF Files
- Classification Web, when available through institutional/subscription access

The free PDF schedules are useful public references. Classification Web is the most current official web-based subscription product.

---

## What Counts as a Good LCC Value

A proposed LCC value is strongest when it is supported by one or more reputable catalog records for the same work or edition.

Preferred evidence order:

1. **Library of Congress catalog record** for the same work or edition.
2. **WorldCat / OCLC-derived library records** showing consistent LCC values.
3. **University or national library catalog records** with matching title, author, and publication details.
4. **Publisher or CIP-style metadata** when catalog records are sparse.
5. **Schedule-derived classification** based on the book's subject, used only when catalog evidence is missing or weak.

The best case is a catalog-confirmed LCC value from the same edition. The next best case is a catalog-consensus LCC value that appears consistently across multiple reputable library records.

---

## Edition Matching

LCC values are most reliable when the record being matched is the same edition or a very close equivalent.

When checking a catalog record, compare:

- Title
- Subtitle
- Author/editor
- Publisher
- Publication year
- ISBN
- Series, if relevant
- Work identity, especially for reprints, translations, revised editions, and dissertations

Older books and public-domain reprints often require extra care. A modern reprint ISBN may not reflect the original cataloged edition. In those cases, the LCC may still be useful for subject placement, but the source should be treated as less edition-specific.

---

## Confidence Levels

The current toolkit does not yet store a formal confidence field, but the methodology uses these working confidence levels.

### Catalog-Confirmed

Use when a reputable catalog record clearly matches the same edition or a near-identical edition.

Typical evidence:

- Same ISBN, title, author, publisher, and year.
- Library catalog provides a specific LCC call number.

### Catalog-Consensus

Use when multiple reputable catalogs agree on the same or very similar LCC, even if the exact edition match is imperfect.

Typical evidence:

- Same work across editions.
- Similar publication details.
- Repeated same call number or same class/subclass across records.

### Schedule-Derived

Use when direct catalog evidence is weak, missing, or inconsistent, but the official LCC schedule and book subject strongly support a class.

Typical evidence:

- Book subject clearly falls under an LCC subclass.
- Catalog records do not provide a useful call number.
- Proposed LCC is derived conservatively.

### Manual Review Recommended

Use when evidence is conflicting, weak, edition identity is unclear, or the book's subject crosses multiple possible classification areas.

Typical triggers:

- Conflicting catalog records.
- Missing ISBN.
- Ambiguous title.
- Dissertation versus later published book confusion.
- Reprint with uncertain original classification.
- Multidisciplinary subject where several LCC classes are plausible.

---

## Field-by-Field Method

### LCC

The raw LCC call number.

Example:

```text
DC203 .E64 2004
```

Preferred method:

1. Search for catalog records matching the work.
2. Prefer same-edition catalog records.
3. If multiple catalog records agree, use the consensus value.
4. If no reliable call number is found, derive conservatively from the LCC schedule and flag for review.

Do not invent precision beyond the available evidence. If a full Cutter/year cannot be supported, the record should be reviewed manually rather than forced.

---

### LCC Primary Class

The top-level LCC class.

Example:

```text
D - World History / History of Europe / Asia / Africa / Australia / New Zealand / Etc
```

Method:

1. Read the leading LCC class letter.
2. Map it to the canonical primary class in `config/lcc-primary-canonical.csv`.
3. Use only approved dropdown values.

Examples:

| LCC | Primary Class |
|---|---|
| `DC203 .E64 2004` | `D - World History / History of Europe / Asia / Africa / Australia / New Zealand / Etc` |
| `HD8390.B73 K63 1990` | `H - Social Sciences` |
| `ND653.G7 S447 2000` | `N - Fine Arts` |

---

### LCC Secondary Class

The controlled second-level LCC subclass bucket.

Example:

```text
DC - France / Andorra / Monaco
```

Method:

1. Read the LCC subclass letters or range.
2. Map the subclass to the canonical secondary dropdown in `config/lcc-secondary-canonical.csv`.
3. Use compact subclass-level labels.
4. Avoid repeating the full primary class text.
5. Use spaced slashes for readability.
6. Avoid commas because Calibre dropdown lists use commas as delimiters.

Examples:

| LCC | Secondary Class |
|---|---|
| `DC203 .E64 2004` | `DC - France / Andorra / Monaco` |
| `HD8390.B73 K63 1990` | `HD - Industries / Land Use / Labor` |
| `ND653.G7 S447 2000` | `ND - Painting` |

---

### LCC Classification Path

A human-readable browsing path.

Example:

```text
D. World History / Europe > DC. France / Andorra / Monaco > France > Napoleonic Era > Napoleon I > Political Life
```

Method:

1. Start with the primary LCC family.
2. Add the secondary subclass.
3. Add deeper subject terms based on the cataloged LCC range and the book's actual subject.
4. Keep the path useful for browsing, not overly technical.
5. Do not overstate certainty when the classification evidence is weak.

This field is local browsing metadata. It is not intended to reproduce every detail of an official LCC schedule.

---

## Handling Conflicts

When sources disagree, prefer the most edition-specific and catalog-authoritative source.

Common conflict handling rules:

| Situation | Preferred Action |
|---|---|
| Same edition, multiple LCC values | Prefer Library of Congress or strongest library consensus |
| Different editions, similar LCC values | Use consensus if subject placement is stable |
| Different editions, conflicting LCC values | Flag for manual review |
| No ISBN | Use title/author/publisher/year match and flag if uncertain |
| Reprint has modern ISBN but original work is older | Use subject-appropriate LCC cautiously |
| Work appears as dissertation and later book | Treat dissertation and book as separate bibliographic objects |

---

## Accuracy Assessment

The current methodology is suitable for high-quality personal Calibre metadata enrichment because it:

- Prefers catalog-confirmed LCC values over generated guesses.
- Uses official LCC structure for primary and secondary class mapping.
- Keeps dropdown values controlled and canonicalized.
- Separates research from metadata application.
- Requires dry run and verification before considering a batch complete.
- Preserves human review before MQG completion.

The methodology is not equivalent to professional original cataloging. It should be treated as a practical, evidence-based local metadata workflow.

---

## Known Risk Areas

### Reprints and Public-Domain Editions

Many older works are available as modern reprints. The ISBN may belong to the reprint, while the LCC may be based on the original work. This is usually acceptable for local subject placement, but should be reviewed if edition precision matters.

### Multidisciplinary Works

Books may sit at the boundary of history, sociology, law, religion, technology, or art. In those cases, catalog consensus matters more than intuition.

### Award Batches

Award program fields may contain multiple values. Calibre search may overmatch. The toolkit's exact Award Programs filter should be used for award batches.

### Sparse Catalog Evidence

Some books have weak or inconsistent public catalog metadata. These should be flagged rather than forced.

---

## Recommended Review Practice

For each completed batch:

1. Run Prepare.
2. Run Validate.
3. Review the dry-run summary.
4. Spot-check several records in the dry-run CSV.
5. Pay special attention to records that had weak source evidence.
6. Apply only if the dry run is clean.
7. Run Verify.
8. Review the verification summary.
9. Manually inspect selected records in Calibre.
10. Mark MQG complete manually only after review.

---

## Future Improvements

Potential future toolkit enhancements:

- Add optional `LCC Source Notes` column.
- Add optional `LCC Confidence` column.
- Add optional `Manual Review` flag.
- Add report section for weak-confidence records.
- Preserve source URLs or catalog names for each proposed LCC.
- Build a reusable source-note format for ChatGPT-generated import files.

These would make the enrichment process more auditable without making the core workflow too heavy.

---

## Reference Anchors

Useful official reference points:

- Library of Congress Classification and Shelflisting:
  `https://www.loc.gov/aba/cataloging/classification/`

- Library of Congress Classification Outline:
  `https://www.loc.gov/aba/cataloging/classification/lcco/`

- Library of Congress Classification PDF Files:
  `https://www.loc.gov/aba/publications/FreeLCC/freelcc`

- Classification Web:
  `https://www.loc.gov/cds/classweb/`

---

## Practical Rule

When in doubt:

```text
Do not force the metadata.
Flag it, review it, and keep the toolkit boring.
```

Boring metadata is good metadata.
