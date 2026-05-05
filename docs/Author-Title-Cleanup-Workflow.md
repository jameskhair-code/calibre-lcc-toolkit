# Author / Title Cleanup Workflow

## 1. Purpose

The Author / Title Cleanup module is the first planned non-LCC module in the Calibre Metadata Toolkit.

Its purpose is to safely review, normalize, dry run, report, apply, and verify title and author metadata changes for selected Calibre records.

This module exists because title and author cleanup should happen early in the broader metadata quality workflow. Cleaner title and author fields improve the reliability of later enrichment steps, including LCC lookup, comments generation, awards cleanup, identifier matching, and future provenance workflows.

The module should remain conservative, reviewable, and boring.

It should not attempt to become a fully automatic metadata correction engine in v0.5.

## 2. Relationship to Existing LCC Workflow

The existing LCC workflow remains stable as of v0.4.

The Author / Title Cleanup module should follow the same safety philosophy:

```text
Export -> External Review -> Dry Run -> Summary -> Apply -> Verify
```

The module should borrow proven patterns from the LCC workflow where useful, but it should remain logically separate.

The LCC module modifies classification-oriented fields.

The Author / Title Cleanup module modifies high-risk core bibliographic fields:

```text
title
authors
```

Because these fields are more visible and more foundational, the module should be especially cautious.

## 3. Read-Only vs Write Operations

### 3.1 Read-Only Operations

The following operations are read-only:

- exporting candidate records
- preparing proposed cleanup TSV files
- validating proposed cleanup TSV structure
- comparing proposed values against current Calibre values
- generating dry-run reports
- generating summary reports
- verifying values after apply

Read-only operations must not modify Calibre metadata.

### 3.2 Write Operations

The following operations modify Calibre metadata:

- applying proposed title changes
- applying proposed author changes

Write operations must only occur through an explicit apply script.

The apply script must require confirmation before making changes.

## 4. v0.5 Scope

The v0.5 goal is to create a safe dry-run/apply workflow for title and author cleanup.

Initial scope:

- export selected records for review
- accept a proposed cleanup TSV
- compare proposed values against current Calibre values
- flag unsafe rows
- produce dry-run and summary reports
- apply only clean approved rows after explicit confirmation
- verify final values after apply

Out of scope for v0.5:

- automatic title correction
- automatic author correction
- web lookup of canonical metadata
- Goodreads reconciliation
- Amazon reconciliation
- LOC authority lookup
- direct SQLite writes
- GUI wrapper
- comments generation
- award cleanup
- identifier/provenance writes

## 5. Recommended Workflow

The planned workflow is:

```text
1. Export candidate records
2. Review exported TSV
3. Prepare proposed cleanup TSV
4. Run dry run
5. Review dry-run report
6. Review summary report
7. Apply approved changes
8. Verify final Calibre values
```

## 6. Input and Output Files

### 6.1 Export File

The export file should contain current Calibre values for review.

Recommended location:

```text
output/author-title-cleanup-export-<batch>.tsv
```

Possible fields:

```text
CalibreId
Title
Authors
ISBN
Identifiers
Series
SeriesIndex
Tags
Published
LastModified
```

The export file is read-only reference material.

### 6.2 Proposed Cleanup TSV

The proposed cleanup TSV should contain original values and proposed values.

Recommended location:

```text
input/author-title-cleanup-import-<batch>.tsv
```

Required fields:

```text
CalibreId
OriginalTitle
ProposedTitle
OriginalAuthors
ProposedAuthors
ChangeReason
Confidence
ManualReviewRequired
```

Optional future fields:

```text
SourceNotes
ReviewerNotes
```

The proposed cleanup TSV is the main review artifact.

### 6.3 Dry-Run Report

The dry-run report should compare the proposed cleanup TSV against current Calibre metadata.

Recommended location:

```text
reports/author-title-cleanup-dryrun-<batch>.csv
```

Possible fields:

```text
CalibreId
CurrentTitle
OriginalTitle
ProposedTitle
TitleChangeDetected
CurrentAuthors
OriginalAuthors
ProposedAuthors
AuthorsChangeDetected
ChangeReason
Confidence
ManualReviewRequired
TitleOriginalMatchesCurrent
AuthorsOriginalMatchesCurrent
ConfidenceStatus
ApplyEligible
BlockingReasons
```

### 6.4 Summary Report

The summary report should provide a batch-level overview.

Recommended location:

```text
reports/author-title-cleanup-summary-<batch>.txt
```

Possible summary metrics:

```text
Total rows reviewed
Rows with title changes
Rows with author changes
Rows with both title and author changes
Rows with no changes
Rows requiring manual review
Rows blocked
Rows eligible for apply
Unexpected confidence values
Original title mismatches
Original author mismatches
Missing CalibreId values
```

### 6.5 Verify Report

The verify report should confirm final Calibre values after apply.

Recommended location:

```text
reports/author-title-cleanup-verify-<batch>.csv
```

Possible fields:

```text
CalibreId
ExpectedTitle
ActualTitle
TitleVerified
ExpectedAuthors
ActualAuthors
AuthorsVerified
VerificationStatus
VerificationNotes
```

## 7. TSV Schema

### 7.1 Required Columns

The v0.5 proposed cleanup TSV should use this required schema:

```text
CalibreId
OriginalTitle
ProposedTitle
OriginalAuthors
ProposedAuthors
ChangeReason
Confidence
ManualReviewRequired
```

### 7.2 Column Definitions

#### CalibreId

The internal Calibre book ID.

This should be the primary target for all writes.

Title and author changes should not be applied based only on ISBN or title matching.

#### OriginalTitle

The title value observed during export/review.

Dry run should compare this value against the current Calibre title before applying.

If `OriginalTitle` does not match the current Calibre title, the row should be blocked.

#### ProposedTitle

The proposed replacement title.

If `ProposedTitle` is blank and `OriginalTitle` is not blank, the row should be blocked unless blanking titles is explicitly supported later.

For v0.5, blank proposed titles should be blocked.

#### OriginalAuthors

The authors value observed during export/review.

Dry run should compare this value against the current Calibre authors before applying.

If `OriginalAuthors` does not match the current Calibre authors, the row should be blocked.

#### ProposedAuthors

The proposed replacement author value.

For v0.5, blank proposed authors should be blocked unless the original authors field was also blank.

#### ChangeReason

A short explanation of why the change is being proposed.

Examples:

```text
Remove subtitle duplication
Normalize author punctuation
Correct OCR/import artifact
Normalize initials
Correct title casing
Remove series text from title
Split title/author contamination
```

#### Confidence

The confidence value assigned to the proposed change.

Allowed values:

```text
High - Mechanical Cleanup
Medium - Evidence Based
Low - Manual Review Recommended
```

#### ManualReviewRequired

Indicates whether the row should be blocked from apply.

Allowed values:

```text
Yes
No
```

Rows with `ManualReviewRequired = Yes` should never be applied automatically.

## 8. Confidence Model

### 8.1 High - Mechanical Cleanup

Use when the cleanup is obvious, local, and mechanical.

Examples:

- remove extra spaces
- remove duplicated punctuation
- normalize title spacing
- remove obvious import artifact
- normalize author separator formatting

### 8.2 Medium - Evidence Based

Use when the cleanup is supported by evidence but not purely mechanical.

Examples:

- correcting title from known catalog form
- correcting author name based on book cover/title page/catalog evidence
- removing subtitle text that clearly belongs elsewhere
- normalizing initials based on known author usage

### 8.3 Low - Manual Review Recommended

Use when the proposed cleanup may be correct but should not be automatically applied.

Examples:

- ambiguous author attribution
- uncertain title/subtitle boundary
- multiple editions with different titles
- translated or alternate title uncertainty
- edited volume with complex contributor roles
- possible pseudonym or variant author name

Rows with this confidence value should normally use:

```text
ManualReviewRequired = Yes
```

## 9. Blocking Rules

The dry run should block apply when any of the following are true:

- `CalibreId` is missing
- `CalibreId` is not found in current Calibre export
- `OriginalTitle` does not match current Calibre title
- `OriginalAuthors` does not match current Calibre authors
- `ProposedTitle` is blank while current title is not blank
- `ProposedAuthors` is blank while current authors is not blank
- `Confidence` is not one of the allowed values
- `ManualReviewRequired` is not `Yes` or `No`
- `ManualReviewRequired = Yes`
- no proposed change exists
- duplicate `CalibreId` values appear in the proposed cleanup TSV

## 10. Apply Eligibility

A row should be apply-eligible only when:

```text
CalibreId exists
OriginalTitle matches current title
OriginalAuthors match current authors
ProposedTitle is valid
ProposedAuthors is valid
Confidence is expected
ManualReviewRequired = No
At least one proposed value differs from the current value
No duplicate target conflict exists
```

## 11. Apply Behavior

The apply script should:

1. Read the proposed cleanup TSV.
2. Re-run safety checks or consume a clean canonical/dry-run artifact.
3. Show a summary of proposed writes.
4. Require explicit confirmation.
5. Apply title and/or author updates by `CalibreId`.
6. Write an apply report.
7. Recommend running verify immediately after apply.

The apply script must be explicit that it modifies Calibre metadata.

## 12. Verification Behavior

The verify script should read current Calibre metadata after apply and compare it against expected proposed values.

Verification should report:

- title matched expected value
- authors matched expected value
- title mismatch
- authors mismatch
- missing Calibre record
- skipped/manual review rows

## 13. Proposed Scripts

Recommended v0.5 scripts:

```text
scripts/Export-CalibreBatchForAuthorTitleCleanup.ps1
scripts/Test-AuthorTitleCleanupDryRun.ps1
scripts/Write-AuthorTitleCleanupSummary.ps1
scripts/Invoke-AuthorTitleCleanupApply.ps1
scripts/Test-AuthorTitleCleanupVerify.ps1
```

Recommended order of implementation:

```text
1. Export-CalibreBatchForAuthorTitleCleanup.ps1
2. Test-AuthorTitleCleanupDryRun.ps1
3. Write-AuthorTitleCleanupSummary.ps1
4. Invoke-AuthorTitleCleanupApply.ps1
5. Test-AuthorTitleCleanupVerify.ps1
```

Apply should not be implemented until export, dry run, and summary are working.

## 14. Possible Script Responsibilities

### 14.1 Export-CalibreBatchForAuthorTitleCleanup.ps1

Purpose:

Export selected records from Calibre for title/author cleanup review.

Should be read-only.

Possible inputs:

```text
LibraryPath
Search
BatchSlug
OutputPath
```

Possible output:

```text
output/author-title-cleanup-export-<batch>.tsv
```

### 14.2 Test-AuthorTitleCleanupDryRun.ps1

Purpose:

Validate proposed title/author cleanup TSV and compare proposed values to current Calibre values.

Should be read-only.

Possible inputs:

```text
LibraryPath
InputPath
ReportPath
```

Possible output:

```text
reports/author-title-cleanup-dryrun-<batch>.csv
```

### 14.3 Write-AuthorTitleCleanupSummary.ps1

Purpose:

Create a human-readable summary from the dry-run report.

Should be read-only.

Possible inputs:

```text
DryRunReportPath
SummaryPath
```

Possible output:

```text
reports/author-title-cleanup-summary-<batch>.txt
```

### 14.4 Invoke-AuthorTitleCleanupApply.ps1

Purpose:

Apply approved title/author cleanup changes to Calibre.

This script modifies Calibre metadata.

Must require explicit confirmation.

Possible inputs:

```text
LibraryPath
InputPath
DryRunReportPath
```

Possible output:

```text
reports/author-title-cleanup-apply-<batch>.csv
```

### 14.5 Test-AuthorTitleCleanupVerify.ps1

Purpose:

Verify current Calibre values after apply.

Should be read-only.

Possible inputs:

```text
LibraryPath
InputPath
VerifyReportPath
```

Possible output:

```text
reports/author-title-cleanup-verify-<batch>.csv
```

## 15. Launcher Integration

Do not immediately replace the existing LCC launcher.

Current launcher:

```text
Start-LccWorkflow.ps1
```

For v0.5, module scripts can be run directly.

A broader launcher can be introduced later, possibly:

```text
Start-CalibreMetadataToolkit.ps1
```

Potential future menu:

```text
1. LCC Workflow
2. Author / Title Cleanup
3. Comments Workflow
4. Identifier / Provenance Workflow
5. Reports
6. Health Check
0. Exit
```

This should wait until the author/title module has working scripts.

## 16. Development Plan for v0.5

Recommended development order:

1. Commit this workflow document.
2. Confirm existing repo structure.
3. Inspect existing LCC scripts for reusable patterns.
4. Create export script.
5. Test export script on a tiny search batch.
6. Create dry-run script.
7. Test dry-run script with a tiny proposed cleanup TSV.
8. Create summary script.
9. Review reports for clarity.
10. Only then create apply script.
11. Create verify script.
12. Update README and changelog.
13. Tag v0.5 after successful end-to-end testing.

## 17. Testing Strategy

Start with tiny batches.

Recommended first test:

```text
1 to 3 records
```

The first test batch should include:

- one title-only cleanup
- one author-only cleanup
- one no-change row
- one manual-review row, if practical

The first apply test should only include safe `High - Mechanical Cleanup` rows.

## 18. Operating Reminder

This module changes core book identity fields.

That means it deserves more caution than a normal enrichment field.

When in doubt:

```text
Do not apply.
Mark manual review.
Fix the TSV.
Dry run again.
Then apply.
```