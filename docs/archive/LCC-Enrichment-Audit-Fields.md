# LCC Enrichment Audit Fields

This document defines the optional audit fields used during Library of Congress Classification (LCC) enrichment runs.

These fields are intended to make the research/enrichment step more transparent and reviewable without adding additional Calibre custom columns yet.

The audit fields are carried through toolkit input and report files, but they are not currently written to Calibre.

---

## Purpose

The LCC enrichment process has two different concerns:

1. What LCC metadata should be applied to the book.
2. How confident we are in that metadata and what evidence supports it.

The toolkit already applies these Calibre metadata fields:

- LCC
- LCC Primary Class
- LCC Secondary Class
- LCC Classification Path

The audit fields help document the reasoning behind those values.

---

## Current Design Decision

For v0.4, the toolkit should support two optional enrichment audit fields:

- LCC Confidence
- LCC Source Notes

These fields are optional.

Older import TSV files that do not include these columns should continue to work normally.

---

## Required Import Fields

A standard completed LCC import TSV should include these required fields:

- Title
- Author
- ISBN
- LCC
- LCC Primary Class
- LCC Secondary Class
- LCC Classification Path

These are the core fields used by the toolkit to validate and apply LCC metadata.

---

## Optional Audit Fields

### LCC Confidence

The confidence level assigned to the proposed LCC metadata.

Allowed values:

- High - Catalog Confirmed
- Medium - Evidence Based
- Low - Manual Review Recommended

The goal is to keep confidence simple and useful. Avoid over-segmenting confidence into too many categories.

### LCC Source Notes

A short free-text explanation of the evidence supporting the proposed LCC metadata.

This should be concise and operationally useful.

Good examples:

    LOC catalog record found for matching ISBN.

    Library catalog consensus supports same LCC class; exact edition match not confirmed.

    No strong catalog record found; schedule-derived from subject. Manual review recommended.

Avoid long research essays inside this field.

---

## Confidence Levels

### High - Catalog Confirmed

Use when there is strong catalog evidence for the same edition or a very close match.

Typical evidence:

- Library of Congress catalog record for the same ISBN or same edition.
- Reputable catalog record with matching title, author, publisher, and year.
- Strong catalog evidence supporting the exact LCC call number.

Expected apply behavior:

- Safe to apply after normal validation.

---

### Medium - Evidence Based

Use when the proposed LCC is supported by real evidence, but the evidence is not quite as strong as High.

Typical evidence:

- Catalog consensus across reputable library records.
- Same work but not necessarily the exact same edition.
- Strong subject alignment with LCC schedule.
- Related editions support the same or very similar classification.

Expected apply behavior:

- Safe to apply after normal review.
- Good candidate for spot-checking if the book is important or unusual.

---

### Low - Manual Review Recommended

Use when evidence is weak, conflicting, uncertain, or mostly schedule-derived.

Typical triggers:

- Conflicting catalog records.
- No strong catalog match.
- No ISBN or ambiguous bibliographic identity.
- Reprint or edition mismatch uncertainty.
- Multidisciplinary subject with multiple plausible LCC classes.
- LCC is mostly inferred from subject rather than catalog evidence.

Expected apply behavior:

- Dry run should complete.
- Summary should clearly report manual-review-needed rows.
- Apply should block by default or warn strongly enough that the batch is not considered ready.

---

## Missing Confidence

If the LCC Confidence column is missing, the toolkit should continue normally.

If the column exists but a row is blank, that row should be counted as:

    Unspecified

Unspecified confidence should not break older workflows, but summaries should make it visible.

---

## Unexpected Confidence Values

If LCC Confidence contains a value outside the approved list, the toolkit should warn.

Approved values are:

- High - Catalog Confirmed
- Medium - Evidence Based
- Low - Manual Review Recommended

Unexpected values should make the batch not ready to apply until corrected.

Examples of values that should be corrected:

- High
- Medium
- Low
- Confirmed
- Guess
- Needs Review
- LOC Confirmed

Use the exact approved text instead.

---

## Source Notes Guidance

LCC Source Notes should summarize the source/evidence basis for the LCC decision.

The field should answer:

    Why do we trust this LCC value?

Good notes are:

- Short
- Plain English
- Evidence-oriented
- Useful during later review

Examples:

    LOC catalog record found for matching ISBN.

    WorldCat/library consensus supports same LCC class; exact edition match not confirmed.

    University catalog record supports this LCC; no LOC record found.

    Schedule-derived from subject due to sparse catalog evidence. Manual review recommended.

---

## Calibre Write Behavior

For v0.4, audit fields should not be written to Calibre.

The only normal write-to-Calibre fields remain:

- LCC
- LCC Primary Class
- LCC Secondary Class
- LCC Classification Path

Audit fields should be carried through:

- completed import TSV
- canonical import TSV
- canonicalization report
- dry-run report
- apply report
- verify report
- summary report

This preserves review context without adding new Calibre columns.

---

## Manual Review Behavior

A row should be treated as requiring manual review when:

    LCC Confidence = Low - Manual Review Recommended

Future script behavior should support this rule:

- Validate can complete.
- Summary should report manual-review-needed rows.
- Apply should not proceed by default when manual-review-needed rows are present.

This preserves safety by preventing low-confidence LCC values from being written accidentally.

---

## Future LOC Identifier Idea

A future branch may explore storing a Library of Congress catalog link or identifier for books that have a matching LOC catalog record.

Possible future fields or behaviors:

- LOC Catalog URL
- LOC Identifier
- Calibre identifier integration
- Clickable link to the matching LOC catalog record

This is intentionally out of scope for v0.4.

Questions to resolve later:

- Which LOC catalog URL format is stable enough?
- Should the LOC link be stored as a Calibre identifier, custom column, or source note?
- Should LOC links only be stored for High-confidence records?
- How does Calibre render custom identifiers as clickable links?

---

## v0.4 Field Contract

Required fields:

- Title
- Author
- ISBN
- LCC
- LCC Primary Class
- LCC Secondary Class
- LCC Classification Path

Optional audit fields:

- LCC Confidence
- LCC Source Notes

Allowed confidence values:

- High - Catalog Confirmed
- Medium - Evidence Based
- Low - Manual Review Recommended

Calibre write fields:

- LCC
- LCC Primary Class
- LCC Secondary Class
- LCC Classification Path

Report-only fields:

- LCC Confidence
- LCC Source Notes

---

## Practical Rule

Keep the audit model lightweight.

If the confidence model becomes confusing, return to the three-level rule:

    High = catalog-confirmed
    Medium = evidence-based
    Low = manual review recommended

The goal is not perfect cataloging bureaucracy.

The goal is safer, clearer, more reviewable LCC enrichment.