# Changelog

All notable changes to the Calibre LCC Toolkit are documented here.

This project uses lightweight version milestones rather than formal semantic versioning. The current milestone pattern is:

    v0.1 = initial working baseline
    v0.2 = accepted functional toolkit
    v0.3 = workflow and documentation polish

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