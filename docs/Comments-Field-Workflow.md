# Comments Field Workflow

## 1. Purpose

The Comments Field Workflow defines the safe operating model for exporting, generating, reviewing, dry-running, applying, and verifying structured HTML comments in Calibre.

This workflow is part of the broader Calibre Metadata Toolkit.

The comments module is intended to generate rich, source-grounded, HTML-formatted comments that make books easier to understand, rediscover, and browse.

The comments field is high-risk because it may contain substantial existing metadata, publisher descriptions, user notes, prior summaries, or other curated content. For that reason, this module must be conservative by default.

The guiding rule is:

```text
Export first.
Dry run first.
Report first.
Apply last.
Verify always.
```

## 2. Relationship to Comments Template Standard

This workflow depends on:

```text
docs/Comments-Template-Standard.md
```

The template standard defines:

- section registry
- template profiles
- HTML conventions
- conditional rendering rules
- length caps
- source notes expectations
- confidence model
- manual review triggers

This workflow document defines how that generated HTML moves safely through the toolkit.

## 3. Workflow Overview

Recommended workflow:

```text
Export -> Generate Proposed Comments -> Dry Run -> Summary -> Apply -> Verify
```

Expanded workflow:

```text
1. Export candidate records from Calibre.
2. Generate or manually prepare proposed comments HTML.
3. Save proposed comments to an import TSV.
4. Run dry run.
5. Review dry-run CSV.
6. Write and review human-readable summary.
7. Apply only when the batch is clean and explicitly confirmed.
8. Verify final Calibre comments after apply.
```

## 4. Read-Only vs Write Operations

## 4.1 Read-Only Operations

The following operations are read-only:

- export candidate records
- inspect existing comments
- generate proposed comments externally
- validate proposed comments TSV
- compare existing comments vs proposed comments
- write dry-run reports
- write summary reports
- verify final values after apply

Read-only operations must not modify Calibre metadata.

## 4.2 Write Operations

The following operation modifies Calibre metadata:

- applying proposed comments HTML to the Calibre `comments` field

Write behavior must only occur through an explicit apply script.

The apply script must require exact confirmation before modifying metadata.

## 5. Planned v0.6 Scope

Initial v0.6 scope should be:

- export selected Calibre records for comments generation
- include current comments and supporting metadata in export
- accept proposed comments HTML in TSV format
- dry run proposed comments against current Calibre values
- detect risky overwrites
- produce a dry-run report
- produce a human-readable summary
- block unsafe rows
- defer apply until dry-run and summary behavior are stable

The initial implementation may stop at export, dry run, and summary before apply is introduced.

## 6. Out of Scope for Initial v0.6

The following should remain out of scope initially:

- automatic web research inside PowerShell
- automatic comments generation inside PowerShell
- automatic companion-read lookup against the full Calibre library
- automatic source citation scraping
- direct SQLite writes
- complex HTML parsing or rendering
- semantic merge of existing and proposed comments
- bulk overwrite of substantial existing comments
- automatic deletion of existing comments
- GUI wrapper
- Calibre plugin packaging

The comments module should initially assume that proposed comments are generated externally through a human-in-the-loop process.

## 7. Proposed Scripts

Recommended script sequence:

```text
scripts/Export-CalibreBatchForComments.ps1
scripts/Test-CommentsDryRun.ps1
scripts/Write-CommentsSummary.ps1
scripts/Invoke-CommentsApply.ps1
scripts/Test-CommentsVerify.ps1
```

Recommended implementation order:

```text
1. Export-CalibreBatchForComments.ps1
2. Test-CommentsDryRun.ps1
3. Write-CommentsSummary.ps1
4. Invoke-CommentsApply.ps1
5. Test-CommentsVerify.ps1
```

Apply should be deferred until export, dry run, and summary are stable.

## 8. Export Workflow

## 8.1 Purpose

The export script should create a source TSV containing enough context to generate proposed comments safely.

The export should be read-only.

## 8.2 Recommended Script

```text
scripts/Export-CalibreBatchForComments.ps1
```

## 8.3 Recommended Output

```text
input/comments-source-{batch}.tsv
```

Example:

```text
input/comments-source-j-russell-major-prize.tsv
```

## 8.4 Recommended Export Fields

The source TSV should include:

```text
CalibreId
Title
Authors
ISBN
Identifiers
Publisher
Published
Series
SeriesIndex
Tags
ExistingComments
ExistingCommentsLength
ExistingCommentsTextPreview
LCC
LCCPrimaryClass
LCCSecondaryClass
LCCClassificationPath
AwardPrograms
AwardNames
AwardEntries
```

Additional fields may be added when useful.

## 8.5 Existing Comments Preview

Because existing comments may be long HTML, the export should include both:

```text
ExistingComments
ExistingCommentsTextPreview
```

`ExistingComments` should contain the full current comments HTML.

`ExistingCommentsTextPreview` should contain a shortened text-only preview to make TSV review easier.

Recommended preview length:

```text
300-500 characters
```

## 9. Proposed Comments Import TSV

## 9.1 Purpose

The proposed comments import TSV is the main human-reviewed artifact.

It should contain original Calibre values, proposed comments HTML, workflow metadata, and safety fields.

## 9.2 Recommended Path

```text
input/comments-import-{batch}.tsv
```

Example:

```text
input/comments-import-j-russell-major-prize.tsv
```

## 9.3 Required Fields

Recommended required fields:

```text
CalibreId
Title
Authors
ExistingCommentsHash
ExistingCommentsLength
ProposedComments
CommentsTemplateProfile
CommentsMode
ChangeReason
Confidence
ManualReviewRequired
SourceNotes
```

## 9.4 Optional Fields

Recommended optional fields:

```text
ExistingCommentsPreview
ProposedCommentsPreview
SectionList
GeneratedBy
GeneratedDate
ReviewerNotes
SourceQuality
ContainsReception
ContainsCompanionReads
ContainsAwards
ContainsSpoilers
```

## 10. Field Definitions

## 10.1 CalibreId

The internal Calibre book ID.

This should be the primary target for all comments writes.

The comments module should not apply changes based only on title, author, or ISBN.

## 10.2 Title

The title value observed during export/review.

The dry run may compare this against current Calibre metadata as a secondary safety check.

If the current title has changed since export, the row should be blocked or flagged for review.

## 10.3 Authors

The authors value observed during export/review.

The dry run may compare this against current Calibre metadata as a secondary safety check.

If the current authors value has changed since export, the row should be blocked or flagged for review.

## 10.4 ExistingCommentsHash

A hash of the existing comments value at export time.

This protects against overwriting comments that changed after export.

Recommended hash:

```text
SHA256
```

If current comments hash does not match `ExistingCommentsHash`, apply should be blocked.

## 10.5 ExistingCommentsLength

The character length of the existing comments HTML at export time.

This helps identify substantial existing comments and supports dry-run reporting.

## 10.6 ProposedComments

The proposed replacement or addition to the Calibre comments field.

This should be valid simple HTML following:

```text
docs/Comments-Template-Standard.md
```

Blank `ProposedComments` means no comments change is proposed and should block apply.

## 10.7 CommentsTemplateProfile

The template profile used to generate the proposed comments.

Allowed values should initially include:

```text
Scholarly Nonfiction
General Nonfiction
Fiction
Reference
Poetry / Drama
Edited Collection / Anthology
Gaming / Technical / Manual
```

Unexpected profile values should block apply or require manual review.

## 10.8 CommentsMode

The intended handling mode for existing comments.

Allowed values:

```text
Replace
Append
Prepend
Skip
```

Future value:

```text
Merge
```

For initial v0.6, `Merge` should not be implemented.

Recommended initial behavior:

- `Replace` is allowed only when existing comments are blank or clearly low-value.
- `Append` may be allowed when existing comments should be preserved.
- `Prepend` may be allowed when generated comments should appear above existing comments.
- `Skip` means no apply should occur for that row.

## 10.9 ChangeReason

A short explanation of why comments are being added or changed.

Examples:

```text
Generate structured comments for award batch
Replace low-value publisher blurb with source-grounded structured comments
Append source notes and reading guidance to existing comments
Create comments for blank record
Manual review after existing comments detected
```

Rows with proposed comments should have a `ChangeReason`.

## 10.10 Confidence

The confidence value assigned to the proposed comments.

Allowed values:

```text
High - Source Grounded
Medium - Source Supported
Low - Manual Review Recommended
```

## 10.11 ManualReviewRequired

Allowed values:

```text
Yes
No
```

Rows with `ManualReviewRequired = Yes` should never be applied automatically.

## 10.12 SourceNotes

A concise source/provenance explanation.

This field may duplicate or summarize the final `<h3>Source Notes</h3>` section in `ProposedComments`.

It is useful for dry-run reporting and audit review.

## 11. Comments Mode Behavior

## 11.1 Replace

`Replace` means the proposed comments will replace existing comments entirely.

This is the highest-risk mode.

Apply should block `Replace` when existing comments are substantial unless explicitly approved.

Recommended blocking threshold:

```text
ExistingCommentsLength >= 300
```

This threshold can be adjusted later.

## 11.2 Append

`Append` means proposed comments will be added after existing comments.

This is safer than replace when existing comments contain useful content.

Recommended output pattern:

```html
{ExistingComments}

<hr />

{ProposedComments}
```

However, because simple HTML is preferred, use of `<hr />` should be reviewed. A simple heading such as `<h3>Generated Notes</h3>` may be preferable.

## 11.3 Prepend

`Prepend` means proposed comments will be placed before existing comments.

Recommended output pattern:

```html
{ProposedComments}

<h3>Existing Notes</h3>
{ExistingComments}
```

This may be useful when generated comments should become the primary visible structure while preserving prior notes.

## 11.4 Skip

`Skip` means no comments write should occur.

Dry run should report the row as skipped.

Apply should not write skipped rows.

## 11.5 Merge

`Merge` means attempting to combine existing and proposed comments intelligently.

This should be deferred.

Initial v0.6 scripts should not implement merge behavior.

## 12. Confidence Model

Allowed confidence values:

```text
High - Source Grounded
Medium - Source Supported
Low - Manual Review Recommended
```

## 12.1 High - Source Grounded

Use when most major claims are supported by strong sources such as:

- publisher page
- library catalog record
- award body record
- author or institutional biography
- table of contents
- reliable review or reception source
- known series/edition information

## 12.2 Medium - Source Supported

Use when comments are mostly supported, but some sections rely on reasonable inference from metadata, subject matter, or limited source coverage.

## 12.3 Low - Manual Review Recommended

Use when:

- source coverage is thin
- book identity is uncertain
- edition identity is uncertain
- reception claims are uncertain
- companion reads are speculative
- existing comments are substantial
- generated HTML may need review
- proposed comments are unusually long
- there is any meaningful doubt

Rows with this confidence should normally use:

```text
ManualReviewRequired = Yes
```

## 13. Dry Run Workflow

## 13.1 Purpose

The dry run should compare proposed comments changes against current Calibre metadata before any writes occur.

The dry run is read-only.

## 13.2 Recommended Script

```text
scripts/Test-CommentsDryRun.ps1
```

## 13.3 Recommended Output

```text
reports/comments-dryrun-{batch}.csv
```

Example:

```text
reports/comments-dryrun-j-russell-major-prize.csv
```

## 13.4 Recommended Dry-Run Fields

```text
CalibreId
Title
Authors
CurrentTitle
CurrentAuthors
TitleMatchesCurrent
AuthorsMatchCurrent
ExistingCommentsLength
CurrentCommentsLength
ExistingCommentsHash
CurrentCommentsHash
CommentsHashMatchesCurrent
ProposedCommentsLength
ProposedCommentsPreview
CommentsTemplateProfile
CommentsTemplateProfileStatus
CommentsMode
CommentsModeStatus
ChangeReason
Confidence
ConfidenceStatus
ManualReviewRequired
SourceNotesPresent
HtmlValidationStatus
ExistingCommentsRisk
ApplyEligible
BlockingReasons
```

## 14. Dry Run Safety Checks

Dry run should block apply when any of the following are true:

- `CalibreId` is missing
- `CalibreId` is not found in current Calibre metadata
- `Title` does not match current Calibre title
- `Authors` does not match current Calibre authors
- `ExistingCommentsHash` does not match current comments hash
- `ProposedComments` is blank
- `ProposedComments` contains obvious placeholder text
- `ProposedComments` contains `DO NOT APPLY`
- `ProposedComments` contains unsupported HTML
- `ProposedComments` appears to contain copied source text or raw pasted blurbs
- `CommentsTemplateProfile` is missing or unexpected
- `CommentsMode` is missing or unexpected
- `CommentsMode = Replace` and existing comments are substantial
- `CommentsMode = Merge`
- `ChangeReason` is blank
- `Confidence` is missing or unexpected
- `ManualReviewRequired` is not `Yes` or `No`
- `ManualReviewRequired = Yes`
- `Confidence = Low - Manual Review Recommended`
- duplicate `CalibreId` values appear in the proposed comments TSV

## 15. HTML Validation

Initial HTML validation should be simple and conservative.

The dry run should flag or block:

```html
<h1>
<h2>
<table>
<div>
<span style="">
<script>
<img>
<iframe>
<style>
```

The dry run should allow:

```html
<h3>
<p>
<ul>
<ol>
<li>
<i>
<em>
<b>
<strong>
<br>
```

The module does not need a full browser-grade HTML parser initially.

A simple string/pattern validator is acceptable for v0.6.

## 16. Placeholder / Unsafe Text Detection

Dry run should block or flag proposed comments containing obvious placeholder text such as:

```text
TODO
TBD
INSERT
PLACEHOLDER
DO NOT APPLY
Lorem ipsum
[fill in]
```

The apply script should always block `DO NOT APPLY` unless a deliberate override exists for testing.

## 17. Existing Comments Risk Model

Existing comments should be treated as valuable.

Recommended initial risk levels:

| Existing Comments State | Risk |
|---|---|
| Blank | Low |
| Very short, low-value text under 300 chars | Low / Medium |
| HTML copied publisher blurb only | Medium |
| Structured existing comments | High |
| Existing comments over 300 chars | High |
| Existing comments containing user notes | High |
| Existing comments containing source notes | High |

The dry run should report the risk level.

Apply should block high-risk existing comments unless manually reviewed.

## 18. Summary Workflow

## 18.1 Purpose

The summary script should convert dry-run CSV data into a readable batch-level report.

The summary is read-only.

## 18.2 Recommended Script

```text
scripts/Write-CommentsSummary.ps1
```

## 18.3 Recommended Output

```text
reports/comments-summary-{batch}.txt
```

Example:

```text
reports/comments-summary-j-russell-major-prize.txt
```

## 18.4 Recommended Summary Metrics

```text
Rows reviewed
Rows eligible for apply
Rows blocked
Rows skipped
Rows with blank existing comments
Rows with substantial existing comments
Rows using Replace
Rows using Append
Rows using Prepend
Rows with unexpected template profile
Rows with unexpected comments mode
Rows with missing confidence
Rows with unexpected confidence
Rows marked manual review
Rows with HTML warnings
Rows with placeholder text
Rows with comments hash mismatch
Rows with duplicate CalibreId
```

The summary should include:

- safety note
- top blocking reasons
- eligible rows preview
- blocked rows preview
- substantial existing comments preview
- recommendation on whether the batch is safe to apply

## 19. Apply Workflow

## 19.1 Purpose

The apply script writes approved comments changes to Calibre.

This script modifies Calibre metadata.

Apply should not be implemented until export, dry run, and summary are stable.

## 19.2 Recommended Script

```text
scripts/Invoke-CommentsApply.ps1
```

## 19.3 Recommended Output

```text
reports/comments-apply-{batch}.csv
```

Example:

```text
reports/comments-apply-j-russell-major-prize.csv
```

## 19.4 Apply Safety Requirements

The apply script must:

- read the dry-run CSV
- refuse to run if any row is blocked
- refuse to run if zero rows are eligible
- refuse to run if any proposed comments contain `DO NOT APPLY`
- re-check current Calibre comments hash before writing
- re-check current title and authors before writing
- show planned changes
- require exact confirmation phrase
- write an apply report
- recommend verification immediately after apply

Recommended confirmation phrase:

```text
APPLY COMMENTS CLEANUP
```

## 19.5 Apply Behavior by CommentsMode

Apply behavior should follow `CommentsMode`.

### Replace

Final comments:

```text
ProposedComments
```

### Append

Final comments:

```text
ExistingComments + separator + ProposedComments
```

### Prepend

Final comments:

```text
ProposedComments + separator + ExistingComments
```

### Skip

No write.

### Merge

Not supported in v0.6.

## 20. Verify Workflow

## 20.1 Purpose

The verify script confirms final comments after apply.

The verify script is read-only.

## 20.2 Recommended Script

```text
scripts/Test-CommentsVerify.ps1
```

## 20.3 Recommended Output

```text
reports/comments-verify-{batch}.csv
```

Example:

```text
reports/comments-verify-j-russell-major-prize.csv
```

## 20.4 Recommended Verify Fields

```text
CalibreId
ApplyEligible
ExpectedCommentsHash
ActualCommentsHash
CommentsVerified
ExpectedCommentsLength
ActualCommentsLength
VerificationStatus
VerificationNotes
```

## 20.5 Verification Status Values

Recommended values:

```text
Verified
Mismatch
Missing
Skipped - Not Apply Eligible
Skipped - CommentsMode Skip
```

## 21. Source Notes Handling

Source Notes should exist in two places:

1. A workflow/report TSV field:

```text
SourceNotes
```

2. A visible final comments section:

```html
<h3>Source Notes</h3>
<ul>
  <li>...</li>
</ul>
```

The workflow field helps review and reporting.

The visible HTML section helps future library browsing.

The dry run should check whether Source Notes are present.

Rows without Source Notes should be flagged or blocked depending on confidence.

Recommended initial behavior:

```text
Missing SourceNotes + High confidence = block
Missing SourceNotes + Medium confidence = block
Missing SourceNotes + Low confidence = block/manual review
```

In other words, Source Notes should be required for v0.6.

## 22. Copyright and Source Safety

The comments workflow should be paraphrase-first.

Dry run should flag content that appears to be copied directly from:

- publisher descriptions
- jacket copy
- marketing blurbs
- long review excerpts
- long author bios

Initial detection can be limited and manual-review oriented.

The summary should remind the user that proposed comments should be original, source-grounded, and not copied wholesale from external sources.

## 23. Companion Reads Safety

Companion Reads are useful but should be conservative.

Manual review should be required when:

- companion reads are not confirmed in the user's library
- companion reads are speculative
- the relationship is weak
- the recommendation depends on unsupported claims

A future module may support library-aware companion-read selection.

For v0.6, Companion Reads should be optional.

## 24. Awards Handling

Awards may appear in comments when relevant.

Award details should be concise.

Recommended section:

```html
<h3>Awards & Recognition</h3>
<ul>
  <li>...</li>
</ul>
```

Award names should not be automatically pushed into Tags.

Award information may come from existing award metadata fields, source TSV fields, or external award records.

## 25. Comments Length Handling

The comments module should report proposed comments length.

Recommended warning thresholds:

| Proposed Comments Length | Behavior |
|---|---|
| 0 chars | Block |
| 1-499 chars | Warn as possibly thin |
| 500-5,000 chars | Normal |
| 5,001-10,000 chars | Warn as long |
| Over 10,000 chars | Block or manual review |

These thresholds can be adjusted after testing.

## 26. Initial Smoke Tests

First dry-run tests should include:

```text
1. Blank existing comments + valid proposed comments + Replace
2. Substantial existing comments + Replace
3. Substantial existing comments + Append
4. Missing SourceNotes
5. Unexpected confidence value
6. ManualReviewRequired = Yes
7. ProposedComments contains DO NOT APPLY
8. ProposedComments contains unsupported HTML
9. Duplicate CalibreId
```

First apply test should only include:

```text
1-2 records
blank or clearly low-value existing comments
High - Source Grounded
ManualReviewRequired = No
CommentsMode = Replace
```

## 27. Recommended v0.6 Development Plan

Recommended sequence:

```text
1. Commit Comments Template Standard.
2. Commit Comments Field Workflow.
3. Build comments export script.
4. Test export against a tiny batch.
5. Build comments dry-run script.
6. Test dry run with synthetic proposed comments TSV.
7. Build comments summary script.
8. Review summary quality.
9. Decide whether v0.6 should include apply or stop at export/dry-run/summary.
10. Only then build apply script if safe.
11. Build verify script after apply.
12. Update README and CHANGELOG.
13. Merge/tag v0.6.
```

## 28. Operating Reminder

Comments are high-value and high-risk.

The module should protect existing comments by default.

When in doubt:

```text
Do not apply.
Mark manual review.
Fix the TSV.
Dry run again.
Review the summary.
Only then apply.
```