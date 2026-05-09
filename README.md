# Calibre Metadata Toolkit

A small PowerShell-based workflow toolkit for improving Calibre book metadata through safe, reviewable, human-in-the-loop workflows.

This repository began as the **Calibre LCC Toolkit**, focused on Library of Congress Classification enrichment. Beginning with the v0.5 development cycle, it is expanding into the broader **Calibre Metadata Toolkit**.

The existing LCC workflow remains the first stable module:

```text
Preflight -> Export -> Enrich -> Prepare -> Validate -> Apply -> Verify
```

The v0.5 development branch adds the first non-LCC module:

```text
Author / Title Cleanup
```

The toolkit is intentionally conservative. Most steps are read-only. Metadata-writing steps are isolated in explicit apply scripts, and those scripts require confirmation before changes are written to Calibre.

---

## What This Toolkit Does

The toolkit currently has two major areas.

### LCC Module

The stable LCC module helps populate these Calibre fields:

| Field | Purpose |
|---|---|
| `LCC` | Raw Library of Congress Classification call number |
| `LCC Primary Class` | Top-level LCC class, such as `H - Social Sciences` |
| `LCC Secondary Class` | Controlled subclass dropdown value, such as `HD - Industries / Land Use / Labor` |
| `LCC Classification Path` | Human-readable classification path for browsing and review |

The LCC workflow also supports optional audit fields during enrichment and reporting:

| Field | Purpose |
|---|---|
| `LCC Confidence` | Indicates how confident the enrichment process is in the proposed LCC metadata |
| `LCC Source Notes` | Short explanation of the evidence/source basis for the proposed LCC metadata |

These audit fields are not currently written to Calibre. They are carried through toolkit input and report files to support review.

The LCC module supports:

- Exporting a selected batch of Calibre records to TSV.
- Preparing an LCC import TSV after enrichment.
- Canonicalizing Primary and Secondary LCC class values against controlled dropdown lists.
- Preserving optional audit fields through the workflow.
- Running a dry run before metadata is changed.
- Writing a readable summary report.
- Applying approved metadata updates.
- Blocking apply when audit fields indicate manual review is required.
- Verifying that Calibre matches the intended import after apply.
- Showing the latest generated report files from the launcher.

### Author / Title Cleanup Module

The v0.5 Author / Title Cleanup module provides a safe workflow for reviewing and cleaning high-risk core bibliographic fields:

| Field | Purpose |
|---|---|
| `title` | Calibre book title |
| `authors` | Calibre author value |

The module supports:

- Exporting candidate records for title/author cleanup review.
- Creating a proposed cleanup TSV.
- Running a dry run before metadata is changed.
- Writing a readable summary report.
- Refusing apply when a dry-run batch contains blocked rows.
- Requiring explicit confirmation before writing changes.
- Verifying final Calibre values after apply.

The Author / Title Cleanup workflow is intentionally conservative because title and author fields affect book identity and downstream metadata enrichment quality.

### Comments Module

The v0.7 Comments module provides a controlled workflow for enriching the standard Calibre Comments field with structured, source-aware HTML curator comments.

The module supports:

- Exporting candidate records with existing comments, comment hashes, LCC context, award context, tags, identifiers, and other useful metadata.
- Preparing proposed comments HTML externally through a human-in-the-loop process.
- Running a dry run against current Calibre metadata.
- Detecting risky existing comments, hash mismatches, missing source notes, unsupported HTML, placeholder text, and unsafe workflow values.
- Writing a readable summary report.
- Creating a visual HTML review page before apply.
- Applying approved comments metadata after explicit confirmation.
- Verifying final Calibre comments after apply.

The Comments workflow is:

    Export -> Generate Proposed Comments -> Dry Run -> Summary -> HTML Review -> Apply -> Verify

The apply step writes to the standard Calibre comments field using a temporary OPF file and `calibredb set_metadata`.

---

## What This Toolkit Does Not Do

This toolkit does not automatically research LCC data by itself.

The intended LCC workflow currently includes an external enrichment step:

```text
Export source TSV -> use ChatGPT/library catalog research to fill LCC data -> save completed import TSV
```

The toolkit then validates and applies that completed import TSV.

The toolkit does not automatically research or correct author/title metadata by itself. The v0.5 Author / Title Cleanup workflow assumes proposed values are reviewed externally before dry run and apply.

The toolkit also does not automatically mark the `MQG-08: LCC` field complete. Final MQG completion remains a manual review step inside Calibre.

The toolkit does not currently write `LCC Confidence` or `LCC Source Notes` into Calibre. Those fields are workflow/report audit fields only.

---

## Requirements

### Required

- Windows
- PowerShell
- Calibre installed locally
- `calibredb.exe`, usually located at:

```text
C:\Program Files\Calibre2\calibredb.exe
```

### Recommended

- Git
- Notepad++
- A recent Calibre database backup before applying metadata changes

---

## Folder Structure

```text
lcc-toolkit/
|-- config/
|   |-- lcc-toolkit.config.json
|   |-- lcc-primary-canonical.csv
|   `-- lcc-secondary-canonical.csv
|-- docs/
|   |-- Author-Title-Cleanup-Workflow.md
|   |-- Comments-Field-Workflow.md
|   |-- Comments-Template-Standard.md
|   |-- LCC-Enrichment-Audit-Fields.md
|   |-- LCC-Methodology.md
|   |-- LCC-Toolkit-Workflow.md
|   `-- Project-Roadmap.md
|-- input/
|   `-- .gitkeep
|-- reports/
|   `-- .gitkeep
|-- scripts/
|   |-- Convert-LccImportToCanonical.ps1
|   |-- Export-CalibreBatchForAuthorTitleCleanup.ps1
|   |-- Export-CalibreBatchForComments.ps1
|   |-- Export-CalibreBatchForLcc.ps1
|   |-- Invoke-AuthorTitleCleanupApply.ps1
|   |-- Invoke-LccImportApply.ps1
|   |-- Show-LccLatestReports.ps1
|   |-- Test-AuthorTitleCleanupDryRun.ps1
|   |-- Test-CommentsDryRun.ps1
|   |-- Test-AuthorTitleCleanupVerify.ps1
|   |-- Test-LccImportDryRun.ps1
|   |-- Test-LccToolkitHealth.ps1
|   |-- Write-AuthorTitleCleanupSummary.ps1
|   |-- Write-CommentsSummary.ps1
|   `-- Write-LccBatchSummary.ps1
|-- Start-LccWorkflow.ps1
|-- CHANGELOG.md
|-- README.md
|-- .gitattributes
`-- .gitignore
```

The repository name and launcher are still LCC-oriented for now. A broader launcher can be introduced after multiple modules are stable.

---

## Important File Types

### LCC Source TSV

A source TSV is exported from Calibre and used for enrichment.

Example:

```text
input/lcc-source-j-russell-major-prize.tsv
```

This file is created by the LCC **Export** step.

### LCC Import TSV

An import TSV contains completed LCC metadata.

Example:

```text
input/lcc-import-j-russell-major-prize.tsv
```

This file is usually created after the source TSV has been enriched with LCC data.

Required import fields:

```text
Title
Author
ISBN
LCC
LCC Primary Class
LCC Secondary Class
LCC Classification Path
```

Optional audit fields:

```text
LCC Confidence
LCC Source Notes
```

### LCC Canonical Import TSV

A canonical import TSV is the normalized version of the completed import TSV.

Example:

```text
input/lcc-import-j-russell-major-prize-canonical.tsv
```

This file is created by the LCC **Prepare** step.

### Author / Title Cleanup Source TSV

An author/title source TSV is exported from Calibre and used for cleanup review.

Example:

```text
input/author-title-cleanup-source-j-russell-major-prize.tsv
```

This file is created by `Export-CalibreBatchForAuthorTitleCleanup.ps1`.

### Author / Title Cleanup Import TSV

An author/title cleanup import TSV contains proposed title and/or author changes.

Example:

```text
input/author-title-cleanup-import-j-russell-major-prize.tsv
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

Blank `ProposedTitle` means no title change is proposed.

Blank `ProposedAuthors` means no author change is proposed.

### Comments Source TSV

A comments source TSV is exported from Calibre and used to prepare proposed structured comments.

Example:

    input/comments-source-j-russell-major-prize.tsv

This file is created by Export-CalibreBatchForComments.ps1.

### Comments Import TSV

A comments import TSV contains proposed comments HTML and review fields.

Example:

    input/comments-import-j-russell-major-prize.tsv

Required fields:

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

For v0.7, this TSV is used for dry run, summary, HTML review, apply, and verify. Comments are still generated externally and reviewed before apply.

### Reports

Reports are written to the `reports` folder.

Common LCC report files:

```text
reports/lcc-canonicalize-j-russell-major-prize.csv
reports/lcc-dryrun-j-russell-major-prize.csv
reports/lcc-summary-j-russell-major-prize-dryrun.txt
reports/lcc-apply-j-russell-major-prize.csv
reports/lcc-verify-j-russell-major-prize.csv
reports/lcc-summary-j-russell-major-prize-verify.txt
```

Common Author / Title Cleanup report files:

```text
reports/author-title-cleanup-dryrun-j-russell-major-prize.csv
reports/author-title-cleanup-summary-j-russell-major-prize.txt
reports/author-title-cleanup-apply-j-russell-major-prize.csv
reports/author-title-cleanup-verify-j-russell-major-prize.csv
```

Common Comments report files:

    reports/comments-dryrun-j-russell-major-prize.csv
    reports/comments-summary-j-russell-major-prize.txt

Generated `input` and `reports` files are ignored by Git.

---

## Batch File Slug

The launcher asks for a **batch file slug**.

Example:

```text
j-russell-major-prize
```

The batch file slug is only used for default filenames. It does not need to match a Calibre field.

For example, the slug:

```text
j-russell-major-prize
```

creates default LCC paths such as:

```text
input/lcc-source-j-russell-major-prize.tsv
input/lcc-import-j-russell-major-prize.tsv
input/lcc-import-j-russell-major-prize-canonical.tsv
reports/lcc-dryrun-j-russell-major-prize.csv
reports/lcc-verify-j-russell-major-prize.csv
```

Author / Title Cleanup files may use similar slugs:

```text
input/author-title-cleanup-source-j-russell-major-prize.tsv
input/author-title-cleanup-import-j-russell-major-prize.tsv
reports/author-title-cleanup-dryrun-j-russell-major-prize.csv
reports/author-title-cleanup-summary-j-russell-major-prize.txt
reports/author-title-cleanup-apply-j-russell-major-prize.csv
reports/author-title-cleanup-verify-j-russell-major-prize.csv
```

Comments files may use similar slugs:

    input/comments-source-j-russell-major-prize.tsv
    input/comments-import-j-russell-major-prize.tsv
    reports/comments-dryrun-j-russell-major-prize.csv
    reports/comments-summary-j-russell-major-prize.txt

Use short lowercase hyphenated names.

Good examples:

```text
j-russell-major-prize
herbert-baxter-adams
marraro-prize
aha-gershoy
nbcc-biography
```

---

## Start the LCC Toolkit Launcher

From the toolkit folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\Start-LccWorkflow.ps1
```

The launcher menu organizes the LCC workflow into phases:

```text
1. Preflight: Run toolkit health check
2. Export: Create source TSV from Calibre
3. Prepare: Canonicalize completed LCC import TSV
4. Validate: Dry run import and write summary
5. Apply: Write approved LCC metadata to Calibre
6. Verify: Confirm final state and write summary
7. Open input folder
8. Open reports folder
9. Open workflow documentation
10. Reports: Show latest report files
11. Show Git status
0. Exit
```

The v0.8 Author / Title Cleanup module is available through the interactive launcher and can also be run through individual scripts.

---

## Standard LCC Workflow

### 1. Preflight

Run:

```text
1. Preflight: Run toolkit health check
```

This checks:

- Toolkit folders
- Config file
- Canonical mapping files
- Required scripts
- `calibredb.exe`
- Whether Calibre appears to be running

Preferred result:

```text
Status: HEALTHY
```

If Calibre is open, close it before exporting or applying metadata.

A warning that Calibre is running is expected if Calibre is open. That warning does not mean the toolkit is broken. It means the toolkit is protecting the workflow.

---

### 2. Export

Run:

```text
2. Export: Create source TSV from Calibre
```

This creates a source TSV from selected Calibre records.

For a normal batch, paste the Calibre search string and leave the exact Award Programs filter blank.

For award batches, a loose Calibre search may overmatch. In that case, use the optional exact Award Programs filter.

Example Calibre search string:

```text
#award_programs:"AHA - J. Russell Major Prize" and #mqg_lcc:false
```

Example exact Award Programs filter:

```text
AHA - J. Russell Major Prize
```

Example output:

```text
input/lcc-source-j-russell-major-prize.tsv
```

This step does not modify Calibre metadata.

---

### 3. Enrich

This is the manual or ChatGPT-assisted research step.

Take the source TSV and produce a completed import TSV with these required columns:

```text
Title
Author
ISBN
LCC
LCC Primary Class
LCC Secondary Class
LCC Classification Path
```

The completed import TSV may also include optional audit fields:

```text
LCC Confidence
LCC Source Notes
```

Allowed `LCC Confidence` values are:

```text
High - Catalog Confirmed
Medium - Evidence Based
Low - Manual Review Recommended
```

Use the values as follows:

| Confidence | Meaning |
|---|---|
| `High - Catalog Confirmed` | Strong catalog evidence supports the proposed LCC metadata |
| `Medium - Evidence Based` | The proposed LCC is supported by evidence, but not as strongly as a direct catalog match |
| `Low - Manual Review Recommended` | Evidence is weak, conflicting, uncertain, or mostly schedule-derived |

Rows marked `Low - Manual Review Recommended` are treated as requiring manual review.

Save the completed import TSV as:

```text
input/lcc-import-{batch}.tsv
```

Example:

```text
input/lcc-import-j-russell-major-prize.tsv
```

---

### 4. Prepare

Run:

```text
3. Prepare: Canonicalize completed LCC import TSV
```

This normalizes the completed import TSV against the canonical Primary and Secondary class lists.

Input example:

```text
input/lcc-import-j-russell-major-prize.tsv
```

Output example:

```text
input/lcc-import-j-russell-major-prize-canonical.tsv
```

Report example:

```text
reports/lcc-canonicalize-j-russell-major-prize.csv
```

This step does not modify Calibre metadata.

The Prepare step also preserves optional audit fields when present:

```text
LCC Confidence
LCC Source Notes
```

Unexpected `LCC Confidence` values are reported as warnings.

---

### 5. Validate

Run:

```text
4. Validate: Dry run import and write summary
```

This checks what would change before anything is written to Calibre.

Input example:

```text
input/lcc-import-j-russell-major-prize-canonical.tsv
```

Dry-run report example:

```text
reports/lcc-dryrun-j-russell-major-prize.csv
```

Summary example:

```text
reports/lcc-summary-j-russell-major-prize-dryrun.txt
```

A ready-to-apply dry run should look like:

```text
Rows: 24
Matched: 24
Warnings: 0
Manual review required: 0
Unexpected confidence: 0
Status: READY TO APPLY
```

The summary also reports LCC audit information when present:

- LCC confidence counts
- LCC confidence status counts
- rows with source notes
- manual-review-required rows
- unexpected-confidence rows

If any row requires manual review, the summary status becomes:

```text
REVIEW REQUIRED
```

Do not apply a batch while the summary says `REVIEW REQUIRED`.

---

### 6. Apply

Run:

```text
5. Apply: Write approved LCC metadata to Calibre
```

This is the metadata-writing step.

Before applying:

- Close Calibre.
- Confirm the dry-run summary says `READY TO APPLY`.
- Confirm the number of matched rows is expected.
- Confirm there are no warnings.
- Confirm `Manual review required` is `0`.
- Confirm `Unexpected confidence` is `0`.

The launcher asks for:

```text
Continue to apply script? Type YES to continue
```

Then the apply script asks for:

```text
APPLY
```

This two-step confirmation is intentional.

### v0.4 LCC Audit Safety Gate

The Apply phase also checks optional LCC enrichment audit fields when they are present.

Apply is blocked by default when either condition is found in the dry-run report:

```text
ManualReviewRequired = Yes
LCCConfidenceStatus = Unexpected
```

This means low-confidence or malformed-confidence rows must be reviewed and corrected before metadata is written to Calibre.

Rows marked:

```text
Low - Manual Review Recommended
```

are treated as requiring manual review and will block Apply by default.

This block happens before the final `APPLY` confirmation prompt, so metadata is not written.

---

### 7. Verify

Run:

```text
6. Verify: Confirm final state and write summary
```

This re-runs the comparison after apply and writes a verification summary.

A successful verification should show:

```text
Rows: 24
Matched: 24
Pending field updates: 0
Warnings: 0
Manual review required: 0
Unexpected confidence: 0
Status: VERIFIED CLEAN
```

That is the end-state win condition.

---


## Canonical MQG Processing Order

The toolkit now uses the following canonical Metadata Quality Gate order:

| Order | Display Label | Stable Lookup Name |
|---:|---|---|
| 1 | MQG-01: Title & Author | `#mqg_title_author` |
| 2 | MQG-02: Identifiers | `#mqg_identifiers` |
| 3 | MQG-03: LCC | `#mqg_lcc` |
| 4 | MQG-04: Awards | `#mqg_awards` |
| 5 | MQG-05: Description / Comments | `#mqg_description` |
| 6 | MQG-06: Tags | `#mqg_tags` |
| 7 | MQG-07: Cover | `#mqg_cover` |
| 99 | MQG-99: Metadata Complete | `#mqg_metadata_complete` |

Only the display labels were reordered.

The lookup names are stable and should not be renamed without a deliberate migration plan.

See:

    docs/MQG-Workflow-Architecture.md

for the current one-pass MQG workflow design.

## Author / Title Cleanup Workflow

The v0.8 Author / Title Cleanup module is available through the interactive launcher and can also be run through individual scripts.

Recommended workflow:

Launcher options:

    A1. Author/Title: Export source TSV
    A2. Author/Title: Dry run cleanup TSV
    A3. Author/Title: Write dry-run summary
    A4. Author/Title: Apply cleanup metadata
    A5. Author/Title: Verify cleanup results
    A6. Author/Title: Mark verified MQG complete

Recommended script workflow:

```text
Export -> Review/Edit Proposed TSV -> Dry Run -> Summary -> Apply -> Verify
```

### Export candidate records

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Export-CalibreBatchForAuthorTitleCleanup.ps1 `
  -Search '#award_programs:"AHA - J. Russell Major Prize"' `
  -ExactAwardProgram "AHA - J. Russell Major Prize" `
  -OutputTsv ".\input\author-title-cleanup-source-j-russell-major-prize.tsv"
```

This is read-only.

### Prepare proposed cleanup TSV

Copy the exported source TSV to an import TSV and fill only the proposed values that should change:

```text
input/author-title-cleanup-import-{batch}.tsv
```

Required columns:

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

Blank `ProposedTitle` means no title change is proposed.

Blank `ProposedAuthors` means no author change is proposed.

Allowed confidence values:

```text
High - Mechanical Cleanup
Medium - Evidence Based
Low - Manual Review Recommended
```

Rows marked `ManualReviewRequired = Yes` are blocked from apply.

### Dry run proposed cleanup

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Test-AuthorTitleCleanupDryRun.ps1 `
  -InputTsv ".\input\author-title-cleanup-import-j-russell-major-prize.tsv" `
  -ReportCsv ".\reports\author-title-cleanup-dryrun-j-russell-major-prize.csv"
```

This is read-only.

### Write summary

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Write-AuthorTitleCleanupSummary.ps1 `
  -DryRunCsv ".\reports\author-title-cleanup-dryrun-j-russell-major-prize.csv" `
  -SummaryTxt ".\reports\author-title-cleanup-summary-j-russell-major-prize.txt"
```

This is read-only.

### Apply approved changes

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Invoke-AuthorTitleCleanupApply.ps1 `
  -DryRunCsv ".\reports\author-title-cleanup-dryrun-j-russell-major-prize.csv" `
  -ApplyReportCsv ".\reports\author-title-cleanup-apply-j-russell-major-prize.csv"
```

This modifies Calibre metadata.

The apply script refuses to run if:

- any row in the dry-run CSV is blocked
- zero rows are eligible
- proposed values contain `DO NOT APPLY`
- current Calibre values changed since the dry run
- the confirmation phrase is not entered exactly

### Verify final values

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Test-AuthorTitleCleanupVerify.ps1 `
  -DryRunCsv ".\reports\author-title-cleanup-dryrun-j-russell-major-prize.csv" `
  -VerifyReportCsv ".\reports\author-title-cleanup-verify-j-russell-major-prize.csv"
```

This is read-only.

---


### LCC verified MQG completion

The LCC workflow includes a separate MQG completion step:

    12. LCC: Mark verified MQG complete

This step updates the Calibre custom field:

    #mqg_lcc

The LCC verify report is the source of truth.

MQG-03: LCC is only considered complete when all four LCC fields are populated and verified:

    LCC
    LCC Classification Path
    LCC Primary Class
    LCC Secondary Class

Eligible rows must have:

- `MatchStatus = Matched`
- a populated `CalibreId`
- no duplicate `CalibreId` in the verify report
- no warnings
- no manual review block
- no unexpected confidence status
- all four existing LCC fields matching their proposed values
- all four `WouldUpdate...` fields set to `No`

The step supports preflight-only mode.

If `#mqg_lcc` is already true, the row is reported as:

    Already Complete

and is not rewritten.

A successful newly marked row requires both the write operation and post-write readback confirmation.





### MQG batch status / readiness report

The toolkit includes a read-only MQG status report:

    13. MQG: Show batch status / readiness report

This step does not modify Calibre metadata.

It reads the current MQG checkbox state for selected Calibre records and writes a batch status report.

The report checks:

- `#mqg_title_author`
- `#mqg_identifiers`
- `#mqg_lcc`
- `#mqg_awards`
- `#mqg_description`
- `#mqg_tags`
- `#mqg_cover`
- `#mqg_metadata_complete`

The report includes:

- completed required gate count
- required gate count
- missing required gates
- ready-for-MQG-99 status
- already-metadata-complete status
- status summary
- blocking reasons

A record is considered ready for MQG-99 when all required MQG gates are complete:

- MQG-01: Title & Author
- MQG-02: Identifiers
- MQG-03: LCC
- MQG-04: Awards
- MQG-05: Description / Comments
- MQG-06: Tags
- MQG-07: Cover

If `#mqg_metadata_complete` is already true, the status summary reports:

    Metadata Complete

This allows the report to distinguish records that are ready for the final gate from records that have already passed it.

### Cover manual MQG completion

The toolkit includes a manual MQG completion step for Cover:

    W2. Cover: Mark reviewed MQG complete

This step updates the Calibre custom field:

    #mqg_cover

This is a manual-gate completion step.

It does not download, generate, replace, or improve cover images. Use it only after the cover has already been manually reviewed.

For records with covers, the step checks:

- the Calibre record exists
- the `cover` field is populated
- the cover path exists on disk
- duplicate Calibre IDs are blocked
- current `#mqg_cover` state can be read back

The step also supports missing/no-cover rows using:

    -AllowNoCover

Only use that option after manual review confirms that a missing cover is acceptable for the current workflow stage.

If `#mqg_cover` is already true, the row is reported as:

    Already Complete

and is not rewritten.

A successful newly marked row requires both the write operation and post-write readback confirmation.

### Awards manual MQG completion

The toolkit includes a manual MQG completion step for Awards:

    W1. Awards: Mark reviewed MQG complete

This step updates the Calibre custom field:

    #mqg_awards

This is a manual-gate completion step.

It does not generate, enrich, or correct award metadata. Use it only after award metadata has already been reviewed.

For records with tracked award recognition, the step checks:

- `Award Programs`
- `Award Entries`
- `Award Designations`
- `Award Years`
- `Award Status - Highest`
- `Award Recognition Count`

The standard pass rule is:

- award metadata exists
- award entries use the expected `Award Designation - Year - Status` shape
- award status is one of `Winner`, `Shortlist`, or `Longlist`
- award recognition count is numeric
- award recognition count matches the number of award entries

The step also supports no-awards / not-applicable rows using:

    -AllowNoAwards

Only use that option after manual review confirms that the book has no tracked award recognition or that award tracking is not applicable for the current workflow stage.

If `#mqg_awards` is already true, the row is reported as:

    Already Complete

and is not rewritten.

A successful newly marked row requires both the write operation and post-write readback confirmation.

### Comments verified MQG completion

The Comments workflow includes a separate MQG completion step:

    C7. Comments: Mark verified MQG complete

This step updates the Calibre custom field:

    #mqg_description

The Comments verify report is the source of truth.

MQG-05: Description / Comments is only considered complete when the comments verify report confirms:

- `ApplyStatus = Succeeded`
- `VerificationStatus = Verified`
- `TitleVerified = Yes`
- `AuthorsVerified = Yes`
- `CommentsVerified = Yes`
- `ExpectedFinalCommentsHash` is populated
- `ActualCommentsHash` is populated
- the expected and actual comments hashes match
- final comments length is greater than zero
- expected and actual comments lengths match

The step supports preflight-only mode.

If `#mqg_description` is already true, the row is reported as:

    Already Complete

and is not rewritten.

A successful newly marked row requires both the write operation and post-write readback confirmation.

## Comments Workflow

The v0.7 Comments module is available through the interactive launcher and can also be run through individual scripts.

Recommended v0.7 workflow:

    Export -> Generate Proposed Comments Externally -> Dry Run -> Summary -> HTML Review -> Apply -> Verify

Launcher options:

    C1. Comments: Export source TSV
    C2. Comments: Dry run import TSV
    C3. Comments: Write dry-run summary
    C4. Comments: Write HTML review
    C5. Comments: Apply comments metadata
    C6. Comments: Verify comments apply report

### Export comments source TSV

Use the launcher option:

    C1. Comments: Export source TSV

Or run directly:

    powershell -ExecutionPolicy Bypass -File .\scripts\Export-CalibreBatchForComments.ps1 `
      -Search "comments:false" `
      -OutputTsv ".\input\comments-source-{batch}.tsv"

The export step is read-only.

You may select books using a Calibre search string, explicit Calibre IDs, or both.

### Generate proposed comments externally

The toolkit does not perform web research or AI generation inside PowerShell.

Use the exported TSV plus:

    docs/Comments-Generation-Prompt-Template.md
    docs/Comments-Template-Standard.md

to generate proposed comments externally.

### Prepare proposed comments TSV

Copy the exported source TSV to an import TSV and fill the proposed comments workflow fields:

    input/comments-import-{batch}.tsv

Required workflow fields include:

    ProposedComments
    CommentsTemplateProfile
    CommentsMode
    ChangeReason
    Confidence
    ManualReviewRequired
    SourceNotes

### Dry run

Use launcher option:

    C2. Comments: Dry run import TSV

Or run directly:

    powershell -ExecutionPolicy Bypass -File .\scripts\Test-CommentsDryRun.ps1 `
      -InputTsv ".\input\comments-import-{batch}.tsv" `
      -ReportCsv ".\reports\comments-dryrun-{batch}.csv"

The dry run is read-only.

Do not apply unless the dry run reports zero blocked rows.

### Summary

Use launcher option:

    C3. Comments: Write dry-run summary

Or run directly:

    powershell -ExecutionPolicy Bypass -File .\scripts\Write-CommentsSummary.ps1 `
      -DryRunCsv ".\reports\comments-dryrun-{batch}.csv" `
      -SummaryTxt ".\reports\comments-summary-{batch}.txt"

### HTML review

Use launcher option:

    C4. Comments: Write HTML review

Or run directly:

    powershell -ExecutionPolicy Bypass -File .\scripts\Write-CommentsReviewHtml.ps1 `
      -InputTsv ".\input\comments-import-{batch}.tsv" `
      -OutputHtml ".\reports\comments-review-{batch}.html" `
      -IncludeExistingComments `
      -Open

Review the rendered HTML before applying.

### Apply comments metadata

Use launcher option:

    C5. Comments: Apply comments metadata

The apply step modifies Calibre metadata.

The launcher defaults to preflight-only mode. Use preflight first, review the report, then run real apply only when the batch is clean.

Direct command example:

    powershell -ExecutionPolicy Bypass -File .\scripts\Invoke-CommentsApply.ps1 `
      -InputTsv ".\input\comments-import-{batch}.tsv" `
      -DryRunCsv ".\reports\comments-dryrun-{batch}.csv" `
      -ApplyReportCsv ".\reports\comments-apply-{batch}.csv"

The apply script requires the exact confirmation phrase before writing.

### Verify comments

Use launcher option:

    C6. Comments: Verify comments apply report

Or run directly:

    powershell -ExecutionPolicy Bypass -File .\scripts\Test-CommentsVerify.ps1 `
      -ApplyReportCsv ".\reports\comments-apply-{batch}.csv" `
      -VerifyReportCsv ".\reports\comments-verify-{batch}.csv"

Verification is read-only.

### Mark verified MQG complete

Use launcher option:

    A6. Author/Title: Mark verified MQG complete

This step updates the Calibre custom field:

    #mqg_title_author

Only rows from the Author / Title verify report with:

    VerificationStatus = Verified

are eligible.

Mismatched, missing, skipped, duplicate, or otherwise unverified rows are not marked complete.

The step requires explicit confirmation:

    MARK MQG COMPLETE

The MQG completion report records:

- rows reviewed
- rows eligible
- rows skipped
- rows marked complete
- rows failed
- readback status

A successful mark requires both the write operation and post-write readback confirmation.

---

## Safety Model

The toolkit is designed around a conservative safety model.

| Area | Operation | Modifies Calibre? |
|---|---|---|
| LCC | Preflight | No |
| LCC | Export | No |
| LCC | Enrich | No |
| LCC | Prepare | No |
| LCC | Validate | No |
| LCC | Apply | Yes |
| LCC | Verify | No |
| Author / Title | Export | No |
| Author / Title | Dry Run | No |
| Author / Title | Summary | No |
| Author / Title | Apply | Yes |
| Author / Title | Verify | No |
| Comments | Export | No |
| Comments | Dry Run | No |
| Comments | Summary | No |

Only explicit Apply scripts write to Calibre.

Apply scripts must require confirmation and must be run only after dry-run reports and summaries are reviewed.

### Audit Fields and Calibre Writes

The LCC audit fields are not written to Calibre in the current design.

Report/workflow fields:

```text
LCC Confidence
LCC Source Notes
```

LCC write-to-Calibre fields:

```text
LCC
LCC Primary Class
LCC Secondary Class
LCC Classification Path
```

Author / Title Cleanup write-to-Calibre fields:

```text
title
authors
```

Comments module write-to-Calibre field:

    comments

For v0.7, the Comments module can write approved proposed comments to Calibre through the controlled apply workflow.

This keeps the Calibre schema clean while still making enrichment and cleanup processes reviewable.

---

## Exact Award Programs Filtering

Calibre award field searches can overmatch when run through `calibredb`.

For example, a loose search such as:

```text
#award_programs:"AHA - J. Russell Major Prize" and #mqg_lcc:false
```

may return more records than intended.

The toolkit supports a local exact filter:

```text
AHA - J. Russell Major Prize
```

The export script first asks Calibre for candidate records, then filters the actual `Award Programs` field exactly.

This is useful for award workflows where the same book may have multiple award program values.

---

## Canonical LCC Dropdowns

The toolkit uses canonical mapping files:

```text
config/lcc-primary-canonical.csv
config/lcc-secondary-canonical.csv
```

These files protect against dropdown mismatches in Calibre.

Examples:

```text
H - Social Sciences
HD - Industries / Land Use / Labor
DC - France / Andorra / Monaco
```

The canonicalization step maps legacy or inconsistent values to the approved dropdown text.

---

## LCC Enrichment Audit Fields

The toolkit supports two optional audit fields:

```text
LCC Confidence
LCC Source Notes
```

These fields are optional. Older TSV files that do not include them should continue to work normally.

### LCC Confidence

Allowed values:

```text
High - Catalog Confirmed
Medium - Evidence Based
Low - Manual Review Recommended
```

Use only those exact values.

Unexpected values, such as `High`, `Medium`, `Low`, `Confirmed`, or `Needs Review`, are reported as unexpected confidence values.

### LCC Source Notes

`LCC Source Notes` should briefly explain why the proposed LCC value is trusted.

Good examples:

```text
LOC catalog record found for matching ISBN.
Library catalog consensus supports same LCC class; exact edition match not confirmed.
Schedule-derived from subject due to sparse catalog evidence. Manual review recommended.
```

Keep source notes short. They are there to help review, not to become a research essay inside a TSV cell.

---

## Reports Viewer

The launcher includes:

```text
10. Reports: Show latest report files
```

This option shows the newest generated report files from the `reports` folder, including dry-run reports, apply reports, verify reports, summary files, canonicalization reports, and health reports.

This is useful during processing runs when you need to quickly confirm which report was just created.

---

## Git Workflow

The project uses Git tags to preserve stable checkpoints.

Current milestone pattern:

```text
v0.1 = original working baseline
v0.2 = accepted toolkit with menu, health check, canonicalization, exact award filtering, apply safety, and verification
v0.3 = workflow label cleanup and documentation polish
v0.4 = operational polish and LCC audit safety gate
v0.5 = author/title cleanup module
v0.6 = comments export, dry run, and summary
v0.7 = comments apply, verify, and launcher integration
v0.8 = author/title cleanup launcher integration
v0.8.1 = author/title explicit ID export support
v0.8.2 = author/title verified MQG completion
v0.8.3 = MQG order alignment
v0.8.4 = LCC verified MQG completion
v0.8.5 = Comments verified MQG completion
v0.8.6 = Awards manual MQG completion
v0.8.7 = Cover manual MQG completion
v0.8.8 = MQG batch status readiness report
```

Useful commands:

```powershell
git status
git log --oneline --decorate --max-count 12
git tag
```

---

## Troubleshooting

### `calibredb` says another Calibre program is running

Close Calibre fully and rerun the command.

Check for Calibre processes:

```powershell
Get-Process calibre* -ErrorAction SilentlyContinue
```

### Exact Calibre search returns zero rows

Try the loose award search without the exact `=` form.

Example:

```text
#award_programs:"AHA - J. Russell Major Prize" and #mqg_lcc:false
```

Then use the toolkit's exact Award Programs filter prompt to narrow results locally.

### A launcher option throws a parameter-binding error

Run the latest version of `Start-LccWorkflow.ps1`. The v0.3+ launcher uses direct named-parameter script calls to avoid argument-passing issues.

### Dry run has unmatched rows

Do not apply.

Check:

- ISBN values
- Calibre records
- Whether the import TSV matches the exported source batch
- Whether any no-ISBN records need manual handling

### Summary says REVIEW REQUIRED

Do not apply.

Review:

```text
reports/lcc-dryrun-{batch}.csv
reports/lcc-summary-{batch}-dryrun.txt
```

Common causes:

- unmatched rows
- multiple matches
- warnings
- `ManualReviewRequired = Yes`
- `LCCConfidenceStatus = Unexpected`

### Apply is blocked by the LCC audit safety gate

This is expected when the dry-run report contains:

```text
ManualReviewRequired = Yes
LCCConfidenceStatus = Unexpected
```

Review and correct the import TSV, rerun Prepare and Validate, then apply only when the summary says `READY TO APPLY`.

### Author / Title Cleanup apply is blocked

This is expected when the dry-run report contains blocked rows or unsafe conditions.

Common causes:

- no proposed title/author change
- `ManualReviewRequired = Yes`
- missing or unexpected confidence value
- original title no longer matches current title
- original authors no longer match current authors
- duplicate `CalibreId`
- proposed values contain `DO NOT APPLY`

Review:

```text
reports/author-title-cleanup-dryrun-{batch}.csv
reports/author-title-cleanup-summary-{batch}.txt
```

Fix the import TSV, rerun dry run, rerun summary, then apply only when the batch is clean.

### Comments dry run blocks all rows

This is expected when running against a raw comments source TSV with no proposed comments.

Common causes:

- missing ProposedComments
- missing CommentsTemplateProfile
- missing CommentsMode
- missing or unexpected Confidence
- missing ManualReviewRequired
- missing SourceNotes
- substantial existing comments with unsafe Replace mode

Review:

    reports/comments-dryrun-{batch}.csv
    reports/comments-summary-{batch}.txt

For v0.7, blocked comments rows must be fixed in the import TSV, then dry-run again. Do not apply until the dry run reports zero blocked rows.

### Verification is not clean

Do not mark the workflow complete yet.

Review LCC verification reports:

```text
reports/lcc-verify-{batch}.csv
reports/lcc-summary-{batch}-verify.txt
```

Review Author / Title Cleanup verification reports:

```text
reports/author-title-cleanup-verify-{batch}.csv
```

---

## Current Human-in-the-Loop Enrichment Model

The toolkit currently assumes this human-in-the-loop model:

1. Export source TSV from Calibre.
2. Use ChatGPT/library catalog research or human review to populate proposed metadata fields.
3. Save the completed import TSV.
4. Let the toolkit validate, summarize, apply, and verify.

For LCC, the external enrichment step populates classification fields.

For Author / Title Cleanup, the external review step populates only proposed title/author changes.

Future versions may add stronger provenance tracking, assisted catalog lookup logic, structured comments generation, or Library of Congress catalog identifiers/links, but the current design intentionally keeps research and metadata writes separate.














