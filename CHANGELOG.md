# Changelog

All notable changes to the Calibre Metadata Toolkit are documented here.

This project uses lightweight version milestones rather than formal semantic versioning. The current milestone pattern is:

    v0.1 = initial working baseline
    v0.2 = accepted functional toolkit
    v0.3 = workflow and documentation polish
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
    v0.8.9 = standard batch manifest support

---

## v0.10.4 - Identifier Proposal Validation

### Added

- Added read-only identifier proposal worksheet validation script:
  - `scripts/Test-IdentifierProposalWorksheet.ps1`

### Behavior

- Reads the identifier proposal worksheet:
  - `.\input\identifier-proposal-worksheet.tsv`
- Writes validation report:
  - `.\reports\identifier-proposal-validation.csv`
- Writes validation summary:
  - `.\reports\identifier-proposal-validation-summary.csv`
- Classifies proposal rows as:
  - `Ready - MQG-02 Completion Preflight`
  - `Manual Review Required`
  - `Blocked - Validation Error`
- Validates required columns, expected status values, yes/no flags, duplicate Calibre IDs, readiness criteria, and strong-core completion eligibility.
- Workflow remains read-only and does not modify Calibre metadata.

### Validated

- Validated identifier proposal worksheet across 5,092 Calibre records.
- Confirmed 3,023 rows ready for MQG-02 completion preflight.
- Confirmed 2,069 rows require manual review.
- Confirmed 0 blocked / validation-error rows.
- Confirmed validation summary preserves proposal action counts:
  - 3,023 `Accept As-Is`
  - 1,169 `Review Missing External Link Targets`
  - 594 `Research Missing ISBN`
  - 238 `Review Missing One External Link Target`
  - 51 `Review Duplicate Identifier`
  - 17 `Review Suspicious Identifier Type`

---
## v0.10.3 - Identifier Proposal Launcher Wiring

### Added

- Added Identifier Module launcher option:
  - `I3. Identifiers: Generate proposal worksheet`

### Behavior

- `I3` runs the read-only identifier proposal worksheet generator:
  - `scripts/New-IdentifierProposalWorksheet.ps1`
- `I3` reads:
  - `.\reports\identifier-mqg02-candidate-summary.csv`
- `I3` writes:
  - `.\input\identifier-proposal-worksheet.tsv`
  - `.\reports\identifier-proposal-summary.csv`
- Workflow remains read-only and does not modify Calibre metadata.

### Validated

- Confirmed launcher displays `Calibre LCC Toolkit v0.10.3`.
- Confirmed Identifier Module now shows:
  - `I1. Identifiers: Export inventory`
  - `I2. Identifiers: Write diagnostics`
  - `I3. Identifiers: Generate proposal worksheet`
- Ran `I3` through the launcher and confirmed:
  - 5,092 rows reviewed
  - 3,023 auto-eligible proposals
  - 2,069 manual-review proposals
  - 3,023 MQG-02 completion candidates

---
## v0.10.2 - Identifier MQG-02 Proposal Framework

### Added

- Added read-only identifier proposal worksheet generator:
  - `scripts/New-IdentifierProposalWorksheet.ps1`

### Behavior

- Reads the MQG-02 candidate diagnostics report:
  - `.\reports\identifier-mqg02-candidate-summary.csv`
- Writes a proposal worksheet:
  - `.\input\identifier-proposal-worksheet.tsv`
- Writes a proposal summary:
  - `.\reports\identifier-proposal-summary.csv`
- Classifies records into proposal actions:
  - `Accept As-Is`
  - `Research Missing ISBN`
  - `Review Missing External Link Targets`
  - `Review Missing One External Link Target`
  - `Review Duplicate Identifier`
  - `Review Suspicious Identifier Type`
- Adds review-oriented proposal fields:
  - `ApprovalStatus`
  - `ManualReviewRequired`
  - `Confidence`
  - `Mqg02CompletionCandidate`
  - `MissingCoreFields`
  - `ProposalBasis`
  - `EvidenceUsed`
  - `ChangeReason`
  - `ReviewerDecision`
  - `ReviewerNotes`
- Workflow remains read-only and does not modify Calibre metadata.

### Validated

- Generated identifier proposal worksheet across 5,092 Calibre records.
- Confirmed 3,023 auto-eligible proposals.
- Confirmed 2,069 manual-review proposals.
- Confirmed 3,023 MQG-02 completion candidates.
- Confirmed proposal action counts:
  - 3,023 `Accept As-Is`
  - 1,169 `Review Missing External Link Targets`
  - 594 `Research Missing ISBN`
  - 238 `Review Missing One External Link Target`
  - 51 `Review Duplicate Identifier`
  - 17 `Review Suspicious Identifier Type`

---
## v0.10.1 - Identifier Launcher Wiring

### Added

- Added Identifier Module options to the interactive launcher:
  - `I1. Identifiers: Export inventory`
  - `I2. Identifiers: Write diagnostics`

### Behavior

- `I1` runs the read-only identifier inventory export workflow.
- `I2` runs the read-only identifier diagnostics workflow.
- Both identifier workflows are accessible from `ctk`.
- Both workflows use default paths for the inventory and diagnostics reports.
- Both workflows remain read-only and do not modify Calibre metadata.

### Validated

- Confirmed launcher displays `Calibre LCC Toolkit v0.10.1`.
- Confirmed Identifier Module appears in the launcher menu.
- Ran `I1` through the launcher and confirmed:
  - 5,092 rows exported
  - 67 identifier types found
  - 261 potential weird rows
- Ran `I2` through the launcher and confirmed:
  - 5,092 rows reviewed
  - 2,020 missing core rows
  - 24 suspicious identifier type rows
  - 47 duplicate ISBN rows
  - 25 duplicate Goodreads rows
  - 29 duplicate Amazon/ASIN rows

---
## v0.10.0 - Identifier Inventory and MQG-02 Rules Foundation

### Added

- Added read-only identifier inventory export script:
  - `scripts/Export-IdentifierInventory.ps1`
- Added read-only identifier diagnostics script:
  - `scripts/Write-IdentifierInventoryDiagnostics.ps1`
- Added MQG-02 Identifier rules documentation:
  - `docs/Identifier-Normalization-Rules.md`
- Added JSON rules profile:
  - `config/identifier-normalization-rules.json`

### Behavior

- Identifier inventory exports one row per Calibre book.
- Inventory captures:
  - ISBN column value
  - ISBN identifier value
  - Amazon identifier
  - ASIN identifier
  - Goodreads identifier
  - identifier type list
  - raw identifier map
  - core coverage flags
- Diagnostics generate reports for:
  - missing core identifiers
  - suspicious identifier type names
  - duplicate ISBN values
  - duplicate Goodreads values
  - duplicate Amazon/ASIN values
  - MQG-02 candidate status summary
- All identifier inventory and diagnostics behavior is read-only.

### Design

- Established first-pass MQG-02 identifier tiers:
  - core identifiers
  - useful identifiers to preserve
  - derived/statistical identifiers
  - suspicious identifier type patterns
- Established initial rules for:
  - ISBN selection
  - Amazon/ASIN handling
  - Goodreads handling
  - duplicate identifier review
  - suspicious identifier type review
  - AI-assisted identifier proposals
  - MQG-02 completion interpretation

### Validated

- Exported identifier inventory across 5,092 Calibre records.
- Confirmed 4,836 books with at least one identifier.
- Confirmed 4,498 books with ISBN.
- Confirmed 3,275 books with Amazon/ASIN.
- Confirmed 3,296 books with Goodreads.
- Generated MQG-02 candidate summary.
- Confirmed first-pass candidate spread:
  - 3,023 Ready - Strong Core
  - 1,169 Review - Missing External Link Targets
  - 594 Review - Missing ISBN
  - 238 Review - Missing One External Link Target
  - 51 Review - Duplicate Identifier
  - 17 Review - Suspicious Identifier Type

---
## v0.9.9 - Author/Title Verify and MQG No-Change Completion Alignment

### Changed

- Updated Author/Title verification to validate clean no-change rows instead of skipping them.
- Added `Clean No-Change` verification status for rows with no proposed/effective title or author changes where current Calibre metadata matches expected values.
- Updated Author/Title MQG completion to mark both:
  - `Verified` rows
  - `Clean No-Change` rows
- Added completion basis reporting to the MQG completion report.

### Behavior

- A5 now reads current Calibre metadata for no-change rows.
- A5 reports clean reviewed no-change rows as `Clean No-Change`.
- A6 now treats `Verified` and `Clean No-Change` rows as eligible for `MQG-01 Title & Author` completion.
- A6 still skips mismatched, missing, duplicate, blocked, or otherwise unsafe rows.
- A6 still requires confirmation before modifying Calibre metadata.

### Validated

- Re-ran A5 against the Andrew Carnegie Medal Author/Title batch.
- Confirmed 86 rows reviewed.
- Confirmed 15 verified changed rows.
- Confirmed 71 clean no-change rows.
- Confirmed 0 mismatched, 0 missing, and 0 skipped rows.
- Re-ran A6 against the v0.9.9 verification report.
- Confirmed 86 rows marked complete.
- Confirmed 0 failed and 0 skipped rows.
- Re-ran MQG batch status.
- Confirmed 0 rows still missing `MQG-01 Title & Author`.

---
## v0.9.8 - Author/Title Apply Alignment

### Changed

- Updated Author/Title apply logic to align with the corrected A2/A3 no-change row model.
- Changed apply blocking logic so only proposed-change rows can block apply.
- No-change rows are now reported separately and ignored by apply.
- Updated apply preview output to show:
  - total dry-run rows
  - no proposed/effective change rows
  - eligible apply rows
  - proposed-change rows blocked
- Updated apply safety wording to clarify that proposed-change rows must be clean.

### Behavior

- A4 now applies rows where `ApplyEligible = Yes`.
- A4 no longer blocks because unchanged rows are present in the dry-run CSV.
- A4 still refuses to apply when any proposed-change row is blocked.
- A4 still performs pre-apply Calibre metadata re-validation before writing.
- A4 still requires the exact confirmation phrase before modifying metadata.

### Validated

- Re-ran A4 against the Andrew Carnegie Medal Author/Title batch.
- Confirmed 86 dry-run rows.
- Confirmed 71 rows with no proposed/effective changes.
- Confirmed 15 rows eligible for apply.
- Confirmed 0 proposed-change rows blocked.
- Applied 15 Author/Title changes.
- Confirmed 15 apply rows succeeded and 0 failed.
- Ran A5 verification.
- Confirmed 15 rows verified, 0 mismatched, 0 missing, and 71 skipped.

---
## v0.9.7 - Author/Title Summary Alignment

### Changed

- Updated Author/Title dry-run summary logic to align with the corrected A2 dry-run validation model.
- Changed summary blocked-row counts so only proposed-change rows can count as blocked.
- Changed blocked-row preview so it only shows proposed-change rows with blockers.
- Changed top blocking reasons so no-change rows do not affect blocker reporting.
- Added no-change row count to the summary console output and batch totals.
- Clarified summary wording from no proposed changes to no proposed/effective changes.

### Behavior

- Rows with no proposed/effective title or author change are counted separately.
- No-change rows are not treated as blocked.
- Summary confidence counts evaluate proposed-change rows only.
- Summary manual-review counts evaluate proposed-change rows only.
- Safety mismatch counts now focus on proposed-change rows.
- Blocked preview reports only proposed-change rows that are actually blocked.

### Validated

- Re-ran the Andrew Carnegie Medal Author/Title summary.
- Confirmed 86 rows reviewed.
- Confirmed 71 rows with no proposed/effective changes.
- Confirmed 15 rows eligible for apply.
- Confirmed 0 blocked rows.
- Confirmed 13 title changes and 2 author changes.
- Confirmed 0 missing confidence values.
- Confirmed 0 unexpected confidence values.
- Confirmed no top blocking reasons.

---
## v0.9.6 - Author/Title Dry-Run Validation Alignment

### Changed

- Updated Author/Title dry-run validation to align with the active Author/Title normalization rules profile.
- Updated accepted confidence values from older long-form labels to:
  - `High`
  - `Medium`
  - `Low`
- Changed no-change rows so they are no longer treated as blocked rows.
- Added a dry-run summary count for rows with no proposed/effective changes.

### Behavior

- Rows with no `ProposedTitle` and no `ProposedAuthors` are treated as no-change rows.
- No-change rows are not apply-eligible, but they are also not blocked.
- Confidence is required only for rows with an actual proposed title or author change.
- Blocking/confidence counts now evaluate proposed-change rows instead of all rows.
- Apply eligibility now requires:
  - an actual proposed title or author change
  - valid confidence
  - `ManualReviewRequired = No`
  - matching current Calibre title/author values
  - no duplicate CalibreId
  - no blocking reasons

### Validated

- Re-ran the Andrew Carnegie Medal Author/Title dry run.
- Confirmed 86 rows reviewed.
- Confirmed 71 rows with no proposed/effective changes.
- Confirmed 15 rows eligible for apply.
- Confirmed 0 blocked rows.
- Confirmed 13 title changes and 2 author changes.
- Confirmed 0 unexpected confidence values.
- Confirmed 0 missing confidence values.

---
## v0.9.5 - Author/Title Normalization Rules Profile

### Added

- Added human-readable Author/Title normalization rules:
  - `docs/Author-Title-Normalization-Rules.md`
- Added machine-readable Author/Title rules config:
  - `config/author-title-normalization-rules.json`
- Added active rules profile reporting to:
  - `G1. Guided Author/Title prep`

### Behavior

- G1 now loads the Author/Title normalization rules config during guided prep.
- G1 operation summaries now record:
  - rules profile name
  - rules profile version
  - rules profile status
  - rules load status
  - rules document path
  - rules config path
- Rules profile v0.1 establishes current Author/Title house-style preferences:
  - normalize author diacritics to keyboard-friendly ASCII
  - remove generic fiction subtitles such as `: A Novel`
  - remove edition, award, and marketing parentheticals
  - keep meaningful nonfiction subtitles
  - keep memoir subtitles by default
  - use ` & ` for multiple authors
  - use First Last author order
  - preserve commonly used initials and hyphenated names
  - mark ambiguous cases for manual review
- Guided Author/Title next-action wording now reflects the AI-assisted proposal workflow instead of implying manual TSV editing as the preferred path.

### Validated

- Confirmed `config/author-title-normalization-rules.json` parses successfully as JSON.
- Confirmed G1 loads the active rules profile.
- Confirmed G1 operation summary includes rules profile details.
- Confirmed parser check passes after launcher updates.

---
## v0.9.4 - Guided Workflow Large Batch Handling

### Added

- Added medium-batch and large-batch handling to:
  - `G1. Guided Author/Title prep`
- Added optional Author/Title review chunk creation for large batches.
- Added review chunk reporting to the guided operation summary.

### Behavior

- `G1` now detects batch size after manifest preview:
  - 1-25 rows: normal guided flow
  - 26-100 rows: medium-batch note
  - 101+ rows: large-batch note and optional review chunk creation
- Large batches can generate smaller Author/Title review chunk TSV files under:
  - `.\input\review-chunks`
- Review chunk files use row-range filenames, such as:
  - `author-title-$batchName-001-050.tsv`
  - `author-title-$batchName-051-100.tsv`
- Operation summaries now include:
  - review chunk count
  - review chunk size
  - review chunk folder
  - row-count warning when manifest row count differs from Author/Title export row count
- Final guided workflow output now lists the review chunk folder when chunk files are created.
- Workflow remains read-only against Calibre metadata.

### Validated

- Confirmed 86-row `search-smoketest` manifest triggers the medium-batch note and creates no review chunks.
- Confirmed temporary 120-row `large-guided-validation` manifest triggers the large-batch path.
- Confirmed large-batch path creates review chunk files.
- Confirmed operation summary records review chunk details and row-count mismatch warning.
- Confirmed final workflow output lists the review chunk folder.

---
## v0.9.3 - Guided Author/Title Prep Workflow

### Added

- Added a new guided workflow:
  - `G1. Guided Author/Title prep`
- Added read-only guided orchestration for Author/Title preparation.

### Behavior

- `G1` can reuse an existing batch manifest or create a new one from:
  - Calibre search string
  - explicit comma-separated Calibre IDs
  - optional exact Award Programs filter
- `G1` performs the following read-only sequence:
  - create or reuse batch manifest
  - preview selected books
  - export Author/Title source TSV
  - generate MQG status/readiness report
  - write operation summary
- `G1` writes an operation summary to:
  - `.\reports\operation-summary-author-title-$batchName.txt`
- Guided workflow output clearly states that Calibre metadata is not modified.

### Validated

- Successfully ran `G1` against the 3-row `idfile-smoketest` manifest.
- Successfully ran `G1` against the 86-row `search-smoketest` manifest.
- Confirmed Author/Title source TSV row counts match the source manifests.
- Confirmed MQG status report row counts match the source manifests.
- Confirmed operation summary files are created with input, file, count, recommendation, and safety details.

---
## v0.9.2 - MQG Status Batch Manifest UX

### Added

- Added `-BatchManifest` support to `scripts/Show-MqgBatchStatus.ps1`.
- Updated launcher option:
  - `13. MQG: Show batch status / readiness report`

### Behavior

- MQG status/readiness reporting can now consume a stable batch manifest created by:
  - `B1. Batch: Create batch manifest`
- Supports batch status selection by:
  - batch manifest CSV with a `CalibreId` column
  - existing input CSV with a `CalibreId` column
  - explicit comma-separated Calibre IDs
- Launcher option `13` now defaults the batch manifest path to:
  - `.\input\batch-$batchSlug.csv`
- Console preview is limited to the first 25 rows while the full report remains available in CSV.
- Operation remains read-only and does not modify Calibre metadata.

### Validated

- Successfully generated a 3-row MQG batch status report from `batch-idfile-smoketest.csv`.
- Successfully generated an 86-row MQG batch status report from `batch-search-smoketest.csv`.
- Confirmed launcher option `13` passes the batch manifest to the MQG status script.
- Confirmed generated report row counts match the source batch manifests.

---
## v0.9.1 - LCC Batch Manifest Consumption

### Added

- Added `-BatchManifest` support to `scripts/Export-CalibreBatchForLcc.ps1`.
- Added explicit `-CalibreIds` support to `scripts/Export-CalibreBatchForLcc.ps1`.
- Updated launcher option:
  - `2. Export: Create source TSV from Calibre`

### Behavior

- LCC export can now consume a stable batch manifest created by:
  - `B1. Batch: Create batch manifest`
- Supports batch selection by:
  - batch manifest CSV with a `CalibreId` column
  - Calibre search string
  - explicit comma-separated Calibre IDs
  - optional exact Award Programs filter
- If a Calibre search and manifest/IDs are both supplied, the manifest/IDs act as a local intersection filter.
- Export remains read-only and does not modify Calibre metadata.

### Validated

- Successfully exported a 3-row LCC source TSV from `batch-idfile-smoketest.csv`.
- Successfully exported an 86-row LCC source TSV from `batch-search-smoketest.csv`.
- Confirmed launcher option `2` passes the batch manifest to the LCC export script.
- Confirmed exported TSV row counts match the source batch manifests.

---
## v0.9.0 - Author/Title Batch Manifest Consumption

### Added

- Added `-BatchManifest` support to `scripts/Export-CalibreBatchForAuthorTitleCleanup.ps1`.
- Updated launcher option:
  - `A1. Author/Title: Export source TSV`

### Behavior

- Author / Title export can now consume a stable batch manifest created by:
  - `B1. Batch: Create batch manifest`
- Supports batch selection by:
  - batch manifest CSV with a `CalibreId` column
  - Calibre search string
  - explicit comma-separated Calibre IDs
  - optional exact Award Programs filter
- If a Calibre search and manifest/IDs are both supplied, the manifest/IDs act as a local intersection filter.
- Export remains read-only and does not modify Calibre metadata.

### Validated

- Successfully exported a 3-row Author / Title source TSV from `batch-idfile-smoketest.csv`.
- Successfully exported an 86-row Author / Title source TSV from `batch-search-smoketest.csv`.
- Confirmed launcher `A1` passes the batch manifest to the export script.
- Confirmed exported TSV row counts match the source batch manifests.

---
## v0.8.9 - Standard Batch Manifest Support

### Added

- Added `scripts/New-ToolkitBatchManifest.ps1`.
- Added launcher section:
  - `Batch Selection Module`
- Added launcher option:
  - `B1. Batch: Create batch manifest`

### Behavior

- Creates a stable CSV batch manifest from one or more supported selection methods:
  - Calibre search string
  - explicit comma-separated Calibre IDs
  - text file containing Calibre IDs
  - optional exact local Award Programs filter
- Treats search plus explicit IDs as an intersection/filter so a searched batch can be narrowed safely.
- Writes the manifest to `./input` by default.
- Writes a batch selection summary report to `./reports` by default.
- Includes key human-review fields such as title, authors, ISBN, identifiers, publisher, publication date, award program, LCC fields, current MQG checkbox state, selection method, source search, and export timestamp.

### Safety

- Read-only operation.
- Does not modify Calibre metadata.
- Blocks empty selection requests.
- Blocks duplicate Calibre IDs in the resolved batch.
- Refuses to overwrite existing manifest/report files unless `-Overwrite` is supplied.
- Reports requested IDs that were not included in the final manifest.

### Notes

- This milestone establishes the batch-selection foundation.
- Direct `-BatchManifest` support in downstream module scripts is intentionally deferred to the next usability-hardening milestone.

---

## v0.8.8 - MQG Batch Status Readiness Report

### Added

- Added `scripts/Show-MqgBatchStatus.ps1`.
- Added launcher option:
  - `13. MQG: Show batch status / readiness report`

### Behavior

- Reads current MQG checkbox state for selected Calibre records.
- Supports input by:
  - comma-separated Calibre IDs
  - CSV with a `CalibreId` column
- Reports current state for:
  - `#mqg_title_author`
  - `#mqg_identifiers`
  - `#mqg_lcc`
  - `#mqg_awards`
  - `#mqg_description`
  - `#mqg_tags`
  - `#mqg_cover`
  - `#mqg_metadata_complete`
- Calculates:
  - completed required gate count
  - missing required gates
  - ready-for-MQG-99 status
  - metadata-complete status
  - status summary
  - blocking reasons

### Safety

- Read-only operation.
- Does not modify Calibre metadata.
- Writes a CSV report for review.

### Validated

- Successfully tested three AHA Leo Gershoy Award records.
- Confirmed all three records had 7 of 7 required gates complete.
- Confirmed all three records were already metadata complete.
- Confirmed launcher wiring and parser checks for `Show-MqgBatchStatus.ps1` and `Start-LccWorkflow.ps1`.

---
## v0.8.7 - Cover Manual MQG Completion

### Added

- Added `scripts/Invoke-CoverMqgComplete.ps1`.
- Added launcher option:
  - `W2. Cover: Mark reviewed MQG complete`

### Behavior

- Marks `#mqg_cover` true only after manual cover review has already been completed.
- Supports input by:
  - comma-separated Calibre IDs
  - CSV with a `CalibreId` column
- Checks that:
  - Calibre record exists
  - cover path is populated
  - cover file exists on disk
  - duplicate Calibre IDs are blocked
- Blocks rows with missing cover paths or missing cover files unless `-AllowNoCover` is explicitly used.
- Detects rows where `#mqg_cover` is already true and reports them as `Already Complete` instead of rewriting them.
- Requires confirmation phrase when new rows need to be marked:

    MARK COVER MQG COMPLETE

### Safety

- Supports preflight-only mode.
- Writes a Cover MQG completion report.
- Performs post-write readback using `calibredb show_metadata --as-opf`.
- Reports `ReadBackStatus = Confirmed true` when the custom field is confirmed true.

### Validated

- Successfully tested three AHA Leo Gershoy Award records.
- Confirmed all three records had cover paths.
- Confirmed all three cover files existed on disk.
- Confirmed all three rows were already complete.
- Confirmed launcher wiring and parser checks for `Invoke-CoverMqgComplete.ps1` and `Start-LccWorkflow.ps1`.

---
## v0.8.6 - Awards Manual MQG Completion

### Added

- Added `scripts/Invoke-AwardsMqgComplete.ps1`.
- Added launcher section:
  - `Manual MQG Completion Module`
- Added launcher option:
  - `W1. Awards: Mark reviewed MQG complete`

### Behavior

- Marks `#mqg_awards` true only after manual award review has already been completed.
- Supports input by:
  - comma-separated Calibre IDs
  - CSV with a `CalibreId` column
- Checks award metadata fields:
  - `Award Programs`
  - `Award Entries`
  - `Award Designations`
  - `Award Years`
  - `Award Status - Highest`
  - `Award Recognition Count`
- Blocks rows with missing or malformed award metadata unless `-AllowNoAwards` is explicitly used.
- Detects rows where `#mqg_awards` is already true and reports them as `Already Complete` instead of rewriting them.
- Requires confirmation phrase when new rows need to be marked:

    MARK AWARDS MQG COMPLETE

### Safety

- Supports preflight-only mode.
- Writes an Awards MQG completion report.
- Performs post-write readback using `calibredb show_metadata --as-opf`.
- Reports `ReadBackStatus = Confirmed true` when the custom field is confirmed true.

### Validated

- Successfully preflighted three AHA Leo Gershoy Award records.
- Confirmed all three rows were eligible.
- Confirmed all three rows were already complete.
- Confirmed launcher wiring and parser checks for `Invoke-AwardsMqgComplete.ps1` and `Start-LccWorkflow.ps1`.

---
## v0.8.5 - Comments Verified MQG Completion

### Added

- Added `scripts/Invoke-CommentsMqgComplete.ps1`.
- Added launcher option:
  - `C7. Comments: Mark verified MQG complete`

### Behavior

- Reads the Comments verify report as the source of truth.
- Marks `#mqg_description` true only for verified Comments rows.
- Requires:
  - `ApplyStatus = Succeeded`
  - `VerificationStatus = Verified`
  - `TitleVerified = Yes`
  - `AuthorsVerified = Yes`
  - `CommentsVerified = Yes`
  - populated expected and actual comments hashes
  - matching expected and actual comments hashes
  - nonzero final comments length
  - matching expected and actual comments lengths
- Skips mismatched, missing, duplicate, failed, skipped, or otherwise unverified rows.
- Detects rows where `#mqg_description` is already true and reports them as `Already Complete` instead of rewriting them.
- Requires confirmation phrase when new rows need to be marked:

    MARK COMMENTS MQG COMPLETE

### Safety

- Supports preflight-only mode.
- Writes a Comments MQG completion report.
- Performs post-write readback using `calibredb show_metadata --as-opf`.
- Reports `ReadBackStatus = Confirmed true` when the custom field is confirmed true.

### Validated

- Successfully preflighted `comments-verify-mixed-v07-smoketest.csv`.
- Confirmed three verified Comments rows were eligible.
- Confirmed two rows were already complete.
- Successfully marked one new row complete.
- Confirmed all three rows reported `ReadBackStatus = Confirmed true`.

---
## v0.8.4 - LCC Verified MQG Completion

### Added

- Added `scripts/Invoke-LccMqgComplete.ps1`.
- Added launcher option:
  - `12. LCC: Mark verified MQG complete`

### Behavior

- Reads the LCC verify report as the source of truth.
- Marks `#mqg_lcc` true only for verified LCC rows.
- Requires all four LCC fields to be populated and verified:
  - `LCC`
  - `LCC Classification Path`
  - `LCC Primary Class`
  - `LCC Secondary Class`
- Skips mismatched, missing, duplicate, warned, manually blocked, or pending-update rows.
- Detects rows where `#mqg_lcc` is already true and reports them as `Already Complete` instead of rewriting them.
- Requires confirmation phrase when new rows need to be marked:

    MARK LCC MQG COMPLETE

### Safety

- Supports preflight-only mode.
- Writes a LCC MQG completion report.
- Performs post-write readback using `calibredb show_metadata --as-opf`.
- Reports `ReadBackStatus = Confirmed true` when the custom field is confirmed true.

### Validated

- Successfully preflighted a 35-row AHA Leo Gershoy LCC verify report.
- Confirmed all 35 rows were eligible.
- Confirmed all 35 rows were already complete with `ReadBackStatus = Confirmed true`.

---
## v0.8.3 - MQG Order Alignment

### Added

- Added `docs/MQG-Workflow-Architecture.md`.

### Changed

- Documented the canonical MQG processing order:
  - `MQG-01: Title & Author`
  - `MQG-02: Identifiers`
  - `MQG-03: LCC`
  - `MQG-04: Awards`
  - `MQG-05: Description / Comments`
  - `MQG-06: Tags`
  - `MQG-07: Cover`
  - `MQG-99: Metadata Complete`
- Updated launcher header to `Calibre LCC Toolkit v0.8.3`.
- Updated toolkit config version to `0.8.3`.

### Notes

- This is a documentation and workflow-alignment release.
- No script behavior changes were made.
- Calibre display labels were reordered manually.
- Stable lookup names remain unchanged and should continue to be used by scripts.

---
## v0.8.2 - Author / Title Verified MQG Completion

### Added

- Added `scripts/Invoke-AuthorTitleMqgComplete.ps1`.
- Added launcher option:
  - `A6. Author/Title: Mark verified MQG complete`

### Behavior

- Reads the Author / Title verify report as the source of truth.
- Only rows with `VerificationStatus = Verified` are eligible.
- Skips mismatched, missing, skipped, duplicate, or otherwise unverified rows.
- Updates the Calibre custom field `#mqg_title_author` to true.
- Requires the confirmation phrase:

    MARK MQG COMPLETE

### Safety

- Supports preflight-only mode.
- Writes a MQG completion report.
- Performs post-write readback using `calibredb show_metadata --as-opf`.
- Reports `ReadBackStatus = Confirmed true` only when the custom field is confirmed true after writing.

### Validated

- Successfully marked three verified Author / Title cleanup records complete.
- Confirmed all three rows reported `MarkStatus = Succeeded`.
- Confirmed all three rows reported `ReadBackStatus = Confirmed true`.

---
## v0.8 - Author / Title Cleanup Launcher Integration

### Added

- Added Author / Title Cleanup Module entries to the interactive launcher:
  - `A1. Author/Title: Export source TSV`
  - `A2. Author/Title: Dry run cleanup TSV`
  - `A3. Author/Title: Write dry-run summary`
  - `A4. Author/Title: Apply cleanup metadata`
  - `A5. Author/Title: Verify cleanup results`

### Changed

- Updated launcher header to `Calibre LCC Toolkit v0.8`.
- Updated toolkit config version to `0.8`.
- Made the Author / Title Cleanup workflow accessible from the launcher rather than requiring hand-run scripts.

### Safety Model

The Author / Title launcher wrappers preserve the existing conservative script behavior.

The apply wrapper does not directly write metadata by itself. It launches the existing apply script only after the user explicitly confirms that they want to continue.

The underlying apply script still requires its own exact confirmation phrase:

    APPLY AUTHOR TITLE CLEANUP

### Notes

- No Author / Title apply-script behavior was changed in v0.8.
- The verify workflow uses the dry-run CSV and writes a verify report.
- This milestone is launcher integration only.

---
## v0.7 - Comments Apply, Verify, and Launcher Integration

### Added

- Added visual comments review support through `scripts/Write-CommentsReviewHtml.ps1`.
- Added comments apply support through `scripts/Invoke-CommentsApply.ps1`.
- Added comments verification support through `scripts/Test-CommentsVerify.ps1`.
- Added `Speculative Fiction` as a supported comments template profile.
- Added v0.7 comments release notes: `docs/Release-v0.7-Comments-Module.md`.
- Added Comments Module entries to the interactive launcher:
  - `C1. Comments: Export source TSV`
  - `C2. Comments: Dry run import TSV`
  - `C3. Comments: Write dry-run summary`
  - `C4. Comments: Write HTML review`
  - `C5. Comments: Apply comments metadata`
  - `C6. Comments: Verify comments apply report`

### Changed

- Promoted the Comments module from read-only validation to a full controlled workflow:

    Export -> Generate Proposed Comments -> Dry Run -> Summary -> HTML Review -> Apply -> Verify

- Updated comments apply behavior to use a temporary OPF file instead of direct `--field comments:<html>` writes.
- Added post-apply re-read behavior so verification uses the Calibre-stored comments hash after Calibre normalizes HTML.
- Added durable generated-comments detection using a visible `Generated By` marker.
- Added idempotent managed comments behavior so regenerated comments replace the generated portion instead of duplicating it.

### Safety Model

The Comments apply script requires:

- a clean dry-run CSV
- zero blocked rows
- matching current title
- matching current authors
- matching current comments hash
- supported `CommentsMode`
- populated `ProposedComments`
- exact confirmation before writing

The apply script writes to the standard Calibre Comments field.

The verify script confirms that current Calibre comments match the expected post-apply stored hash.

### Validated

- Successfully applied and verified generated comments against an existing-comments record.
- Successfully applied and verified generated-only comments against a blank-comments record.
- Successfully applied and verified a mixed-state three-record smoke test.
- Confirmed original comments are preserved under `Original Comments` when existing comments are present.
- Confirmed generated-only records do not create an unnecessary `Original Comments` section.
- Confirmed the launcher displays the v0.7 Comments Module menu and exits cleanly.

### Notes

- v0.7 does not automate web research or comments generation inside PowerShell.
- Proposed comments remain human-reviewed before apply.
- Generated workflow files remain ignored by Git.

---
## v0.6 - Comments Export, Dry Run, and Summary

### Added

- Added Comments Template Standard documentation: docs/Comments-Template-Standard.md.
- Added Comments Field Workflow documentation: docs/Comments-Field-Workflow.md.
- Added read-only comments export script: scripts/Export-CalibreBatchForComments.ps1.
- Added read-only comments dry-run script: scripts/Test-CommentsDryRun.ps1.
- Added read-only comments summary script: scripts/Write-CommentsSummary.ps1.

### Changed

- Clarified that v0.6 is intentionally limited to comments export, dry run, and summary.
- Deferred comments apply and verify behavior to a later milestone, such as v0.6.1 or v0.7.
- Updated documentation to describe the comments module as a source-grounded, type-aware, HTML-simple workflow.
- Defaulted comments export CommentsMode to blank so replace/append/prepend decisions must be intentional.

### Safety Model

v0.6 does not write comments to Calibre.

The Comments module currently supports:

    Export -> Dry Run -> Summary

The dry-run script blocks unsafe or incomplete rows, including:

- missing proposed comments
- missing SourceNotes
- missing or unexpected template profile
- missing or unexpected comments mode
- missing or unexpected confidence
- manual review rows
- comments hash mismatches
- duplicate CalibreId values
- unsupported HTML
- placeholder or DO NOT APPLY text
- high-risk existing comments with Replace mode

### Validated

- Successfully exported a 24-record comments source TSV from the AHA - J. Russell Major Prize batch.
- Successfully ran a no-proposed-comments dry run and summary.
- Confirmed all raw source rows were blocked as expected.
- Confirmed all 24 source rows were identified as high-risk existing comments due to substantial existing comments.
- Successfully ran a synthetic proposed-comments smoke test with eligible Append/Prepend rows.
- Successfully confirmed blocking for high-risk Replace, missing SourceNotes, unsupported HTML, and placeholder text.

### Notes

- v0.6 does not add new Calibre custom columns.
- v0.6 does not automate web research or comments generation.
- v0.6 does not apply comments to Calibre.
- Proposed comments remain human-reviewed before any future apply behavior is added.

## v0.5 - Author / Title Cleanup Module

### Added

- Added project roadmap documentation: `docs/Project-Roadmap.md`.
- Added Author / Title Cleanup workflow documentation: `docs/Author-Title-Cleanup-Workflow.md`.
- Added read-only author/title cleanup export script: `scripts/Export-CalibreBatchForAuthorTitleCleanup.ps1`.
- Added read-only author/title cleanup dry-run script: `scripts/Test-AuthorTitleCleanupDryRun.ps1`.
- Added read-only author/title cleanup summary script: `scripts/Write-AuthorTitleCleanupSummary.ps1`.
- Added author/title cleanup apply script: `scripts/Invoke-AuthorTitleCleanupApply.ps1`.
- Added read-only author/title cleanup verify script: `scripts/Test-AuthorTitleCleanupVerify.ps1`.

### Changed

- Broadened project identity from `Calibre LCC Toolkit` toward `Calibre Metadata Toolkit`.
- Kept the existing LCC workflow as the first stable module.
- Preserved the existing repository name and launcher for now.
- Updated README documentation to describe both the LCC module and the Author / Title Cleanup module.

### Safety Model

The Author / Title Cleanup module follows the same conservative workflow philosophy as the LCC module:

```text
Export -> Dry Run -> Summary -> Apply -> Verify
```

The export, dry-run, summary, and verify scripts are read-only.

The apply script modifies Calibre metadata, but only after safety checks pass and the exact confirmation phrase is entered.

Apply is refused when:

- any row in the dry-run CSV is blocked
- zero rows are eligible for apply
- proposed values contain `DO NOT APPLY`
- current Calibre metadata changed after the dry run
- the confirmation phrase is not entered exactly

### Validated

- Successfully exported a 24-record author/title cleanup source TSV from the AHA - J. Russell Major Prize batch.
- Successfully ran a no-change dry run and summary.
- Successfully ran a smoke-test dry run with:
  - title-change detection
  - author-change detection
  - no-change blocking
  - manual-review blocking
- Successfully confirmed apply refusal on a dirty smoke-test batch.
- Successfully ran verification against unapplied smoke-test changes and confirmed expected mismatches/skips.

### Notes

- v0.5 does not add new Calibre custom columns.
- v0.5 does not automate author/title research.
- Proposed title/author changes remain human-reviewed before apply.
- The broader launcher is deferred until multiple modules are stable.

---

## v0.4 - Operational Polish and LCC Audit Safety

### Added

- Added latest reports viewer script: `scripts/Show-LccLatestReports.ps1`.
- Added launcher option to show latest generated report files.
- Added health-check coverage for the latest reports viewer script.
- Added `docs/LCC-Enrichment-Audit-Fields.md`.
- Added optional LCC enrichment audit field support:
  - `LCC Confidence`
  - `LCC Source Notes`

### Changed

- Updated canonicalization workflow to preserve optional audit fields.
- Updated dry-run reports to carry audit fields forward.
- Updated summary reports to include:
  - LCC confidence counts
  - confidence status counts
  - source-notes presence count
  - manual-review-required count
  - unexpected-confidence count
- Updated apply safety behavior so metadata writes are blocked when audit review is required.

### Safety Gate

Apply is now blocked by default when either condition is present in the dry-run report:

- `ManualReviewRequired = Yes`
- `LCCConfidenceStatus = Unexpected`

This prevents low-confidence or malformed-confidence LCC enrichment rows from being written to Calibre accidentally.

### Notes

- v0.4 does not add new Calibre custom columns.
- Audit fields are currently report/workflow fields only.
- The normal write-to-Calibre fields remain:
  - `LCC`
  - `LCC Primary Class`
  - `LCC Secondary Class`
  - `LCC Classification Path`

---

## v0.3 - Workflow and Documentation Polish

### Added

- Added GitHub-ready `README.md`.
- Added `docs/LCC-Methodology.md`.
- Updated `docs/LCC-Toolkit-Workflow.md` to match the phase-based workflow.
- Added clearer documentation for the human-in-the-loop LCC enrichment process.
- Added explicit methodology guidance for:
  - catalog-confirmed LCC values
  - catalog-consensus LCC values
  - schedule-derived LCC values
  - manual review cases
  - reprints and older books
  - no-ISBN records
  - award batch filtering

### Changed

- Refined the launcher menu around the phase model:

    Preflight -> Export -> Enrich -> Prepare -> Validate -> Apply -> Verify

- Renamed launcher menu labels to be more user-facing and less script-oriented.
- Combined dry run and summary generation into the Validate phase.
- Combined final verification and summary generation into the Verify phase.
- Clarified that the batch file slug is only used for default filenames.
- Clarified that only the Apply phase modifies Calibre metadata.

### Notes

- v0.3 is focused on usability, clarity, and documentation.
- No major changes were made to the underlying metadata application model.

---

## v0.2 - Accepted Functional Toolkit

### Added

- Added interactive launcher: `Start-LccWorkflow.ps1`.
- Added toolkit health check: `scripts/Test-LccToolkitHealth.ps1`.
- Added LCC import canonicalization script: `scripts/Convert-LccImportToCanonical.ps1`.
- Added batch summary writer: `scripts/Write-LccBatchSummary.ps1`.
- Added central config file: `config/lcc-toolkit.config.json`.
- Added canonical LCC Primary Class mapping file.
- Added canonical LCC Secondary Class mapping file.
- Added repository line ending rules with `.gitattributes`.
- Added config and docs folders.
- Added exact Award Programs filtering to the export workflow.

### Changed

- Added explicit `APPLY` confirmation before metadata updates.
- Reduced noisy console output from the apply script.
- Improved launcher prompts.
- Updated launcher argument handling to use direct named-parameter calls.
- Improved path handling for health checks and workflow scripts.
- Preserved generated input and report files outside Git tracking through `.gitignore`.

### Validated

- Successfully ran full acceptance workflow against the AHA - J. Russell Major Prize batch.
- Exported a 24-record exact-filtered award batch.
- Canonicalized import TSV.
- Ran dry run.
- Generated summary.
- Applied approved metadata.
- Verified final state.
- Confirmed final verification was clean.

### Notes

- v0.2 is the first accepted functional milestone.
- `main` and tag `v0.2` point to this stable toolkit baseline.

---

## v0.1 - Initial Working Baseline

### Added

- Added initial working script set:
  - `scripts/Export-CalibreBatchForLcc.ps1`
  - `scripts/Test-LccImportDryRun.ps1`
  - `scripts/Invoke-LccImportApply.ps1`
- Added input and reports folders.
- Added `.gitignore`.
- Established Git repository baseline.
- Tagged initial working state as `v0.1`.

### Validated

- Successfully processed the AHA - Herbert Baxter Adams Prize test batch.
- Confirmed export, dry run, apply, and verification workflow worked manually.

### Notes

- v0.1 was a working baseline, but still required more manual command knowledge.
- v0.2 built on this by adding a launcher, health checks, canonicalization, and stronger safeguards.
























