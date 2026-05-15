# Identifier Normalization Rules

Profile name: Keith Identifier Normalization Rules  
Profile version: v0.2  
Scope: MQG-02 Identifiers + Maintenance (clean-identifiers)  
Status: ActiveDraft  
Last updated: 2026-05-15

---

## 1. Purpose

The Identifier workflow supports MQG-02 by reviewing, normalizing, enriching, and validating book identifiers in Calibre.

Identifiers are used for:

- Calibre hyperlinking to external book/product pages
- metadata lookup and enrichment
- deduplication support
- title/author anomaly resolution
- evidence-backed AI proposal generation
- future comments/tags/classification enrichment

MQG-02 should not be treated as a simple presence check. It should determine whether a record has trustworthy, useful, correctly-shaped identifiers or an explicit reviewed exception.

---

## 2. Core Identifier Types

The first-pass core identifier set is:

- `isbn`
- `amazon`
- `mobi-asin`
- `goodreads`

### Notes

- `isbn` is the primary bibliographic anchor.
- `amazon` and `mobi-asin` are the Amazon-linking identifiers used in this library.
  `asin` is removed by `clean-identifiers` (low coverage, superseded by `amazon`/`mobi-asin`).
- `goodreads` is the book-discovery / external-linking identifier.

---

## 3. Useful Identifier Types to Preserve

These identifiers are useful and should generally be preserved unless clearly malformed or wrong:

- `google`
- `barnesnoble`
- `fictiondb`
- `ff`
- `oclc`
- `oclc-worldcat`

`oclc` and `oclc-worldcat` are kept because they are candidates for future enrichment.

## 3a. Types Removed by clean-identifiers (maintenance rules)

The following types are removed automatically by the `clean-identifiers` maintenance command:

**DRM / plugin artifacts:** `acs6`, `epubbud`, `notes_images`, `revision`, `ligmd5`

**Typos / ambiguous:** `oasin`

**URL / URI noise** (import artifacts, not useful for lookup): `url`, `url2`, `url3`, `uri`, `urn`, `access_url`, `ark`

**Store identifiers not used in this library's workflow:** `ozon`, `epl`, `ilot`, `guid`, `ltid`, `amazon_uk`, `sonybookid`

**Low-coverage retail store identifiers:** `asin` (21 books — superseded by `amazon`/`mobi-asin`), `kobo` (16 books)

**ISBN variants** (normalize or remove in favour of `isbn`): `eisbn`, `ean`, `isbn10`, `isbn13`, `isbn-10`

**Specialist databases with negligible coverage:** `isfdb` (1 book), `isfdb-title` (1 book), `lccn` (8 books)

**Academic/archive identifiers not relevant to this collection:** `doi`

**LibraryThing:** `ltid`

---

## 4. Derived / Statistical Identifier Types

These should generally be preserved but should not make or break MQG-02 completion:

- `grrating`
- `grvotes`

They are useful metadata, but they are not identity anchors.

---

## 5. Suspicious Identifier Type Names

Identifier type names should not themselves be ISBNs, URNs, or malformed pseudo-fields.

The following patterns are auto-corrected by `clean-identifiers`:

| Pattern | Example | Action |
|---|---|---|
| `urnisbn/<isbn>` as type | `urnisbn/9781409016571` | Normalize to `isbn:<isbn>` (or remove if `isbn` present) |
| `urnuuid/<anything>` as type | `urnuuid/0395856973` | Remove |
| `isbn<10 or 13 digits>` as type | `isbn9780007462520` | Normalize to `isbn:<digits>` (or remove if `isbn` present) |
| `p<10 or 13 digits>` as type | `p9780299300234` | Normalize to `isbn:<digits>` (or remove if `isbn` present) |
| `isbn10`, `isbn13`, `isbn-10` | `isbn13` | Normalize to `isbn` (or remove if `isbn` present) |

Bare ISBN-looking type names (e.g. `9780061760358` as a type with no prefix) are not yet auto-detected and should be handled manually.

---

## 6. ISBN Rules

### 6.1 Preferred ISBN

Prefer ISBN-13 when available.

Use ISBN-10 only when:

- no ISBN-13 is available, or
- the ISBN-10 is the only reliable identifier currently available, or
- the ISBN-10 appears to represent the actual edition and no safe ISBN-13 conversion/confirmation exists.

### 6.2 Multiple ISBNs

When multiple ISBNs are present:

- Prefer the ISBN associated with the actual edition represented in Calibre.
- If edition cannot be determined, flag for human review.
- Do not replace an existing valid ISBN unless the proposed ISBN is clearly better.

### 6.3 ISBN Validity

A valid ISBN candidate should look like:

- ISBN-13: 13 digits, commonly beginning with `978` or `979`
- ISBN-10: 10 characters, allowing final `X`

Hyphens/spaces may be normalized away for validation.

### 6.4 ISBN as Title

If a title appears to be an ISBN:

- Treat it as an anomaly.
- Use it as evidence, not proof.
- Attempt reconstruction using identifiers, existing author, and external sources where available.
- Require human review unless evidence is very strong.

---

## 7. Amazon / ASIN Rules

Amazon-like identifiers include:

- `amazon`
- `asin`
- `mobi-asin`

A valid ASIN is usually a 10-character alphanumeric value.

### 7.1 Preservation

Preserve existing Amazon/ASIN identifiers unless clearly malformed or wrong.

### 7.2 Selection

Prefer the identifier that resolves to the intended book/edition when known.

If multiple Amazon-like identifiers exist:

- Prefer exact title/author match.
- Prefer book/product page over unrelated media/product pages.
- Flag ambiguous cases for review.

### 7.3 Missing Amazon

Missing Amazon/ASIN should not automatically block MQG-02 completion if:

- ISBN and/or Goodreads are strong,
- no confident Amazon match exists,
- and the record is explicitly accepted as-is.

---

## 8. Goodreads Rules

A Goodreads identifier should normally be numeric.

### 8.1 Preservation

Preserve existing Goodreads IDs unless clearly malformed or wrong.

### 8.2 Selection

Prefer exact title/author match.

If a work has many editions:

- Prefer the identifier already present if it appears plausible.
- Prefer the edition/work page only when mapping is obvious.
- Flag ambiguous cases for review.

### 8.3 Missing Goodreads

Missing Goodreads should not automatically block MQG-02 completion if:

- ISBN and/or Amazon are strong,
- no confident Goodreads match exists,
- and the record is explicitly accepted as-is.

---

## 9. Duplicate Identifier Rules

Duplicate identifiers should be reviewed before MQG-02 completion.

Duplicates may represent:

- duplicate Calibre records
- alternate title/subtitle normalization
- multi-volume works
- legitimate same-work records
- actual metadata errors

Default action:

- Flag duplicate ISBN, Goodreads, and Amazon/ASIN values for review.
- Do not auto-remove duplicates.
- If duplicates are legitimate, allow `Accepted As-Is`.

---

## 10. MQG-02 Candidate Statuses

Recommended statuses:

- `Ready - Strong Core`
- `Review - Missing ISBN`
- `Review - Missing External Link Targets`
- `Review - Missing One External Link Target`
- `Review - Duplicate Identifier`
- `Review - Suspicious Identifier Type`
- `Accepted As-Is`
- `Blocked - Conflicting Evidence`

---

## 11. Apply Safety Model

Identifier changes should follow the same safety model as Author/Title cleanup:

1. Export inventory/source data.
2. Generate proposals.
3. Dry run proposals.
4. Write summary.
5. Apply approved changes only.
6. Verify current Calibre metadata.
7. Mark MQG-02 complete only for verified or accepted-as-is rows.

No AI-generated identifier should be applied without a dry run and a reviewable report.

---

## 12. AI Proposal Rules

AI may assist with:

- identifying missing ISBNs
- identifying Amazon/ASIN values
- identifying Goodreads IDs
- recovering malformed ISBN-like identifier type names
- flagging duplicates and suspicious values
- generating human-readable evidence summaries

AI must not blindly overwrite existing identifiers.

Proposal rows should include:

- CalibreId
- Title
- Authors
- ExistingIdentifiers
- ProposedIdentifierType
- ProposedIdentifierValue
- Action
- EvidenceUsed
- Confidence
- ManualReviewRequired
- ApprovalStatus
- ChangeReason

Only high-confidence, non-manual-review proposals should be eligible for normal apply.

---

## 13. Initial MQG-02 Interpretation

A record can be considered MQG-02 complete when:

- it has a valid ISBN or an explicit reviewed exception,
- it has no unresolved suspicious identifier type,
- it has no unresolved duplicate identifier conflict,
- available Amazon/ASIN and Goodreads identifiers are preserved or populated when confidently known,
- missing external identifiers are accepted as-is when no confident match exists.

