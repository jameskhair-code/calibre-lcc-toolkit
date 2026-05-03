# Calibre LCC Toolkit Workflow

## Purpose

The Calibre LCC Toolkit supports repeatable Library of Congress Classification enrichment for Calibre book records.

The toolkit helps with:

- Exporting a batch of Calibre records for LCC enrichment.
- Preparing an import TSV with LCC metadata.
- Validating proposed LCC Primary and Secondary Class values against canonical dropdown lists.
- Running a dry run before applying changes.
- Applying verified LCC updates.
- Verifying that Calibre matches the intended import file after apply.

## Current Version

Toolkit version: `v0.2`

The `v0.1` baseline is preserved as a Git tag.

## Managed Calibre Fields

The toolkit manages these fields:

| Field | Purpose |
|---|---|
| `LCC` | Raw Library of Congress Classification call number |
| `LCC Primary Class` | Top-level LCC class |
| `LCC Secondary Class` | Compact controlled subclass bucket |
| `LCC Classification Path` | Human-readable deeper classification path |

## Canonical LCC Model

### LCC

Raw call number.

Example:

```text
HD8390.B73 K63 1990
```

### LCC Primary Class

Broad 10,000-foot LCC category.

Example:

```text
H - Social Sciences
```

### LCC Secondary Class

Compact controlled dropdown value.

Example:

```text
HD - Industries / Land Use / Labor
```

### LCC Classification Path

Deeper human-readable hierarchy.

Example:

```text
H. Social Sciences > HD. Industries / Land Use / Labor > Labor > Working Class and Industrial Society > England / Bradford > Class Formation 1750-1850
```

## Standard Workflow

1. Close Calibre.
2. Export a source batch from Calibre.
3. Enrich the batch with LCC data.
4. Convert / validate the import file against canonical dropdown values.
5. Run a dry run.
6. Review the dry-run report.
7. Apply only after the dry run looks correct.
8. Verify final state.
9. Manually review selected records in Calibre.
10. Manually mark `MQG-08: LCC` complete when satisfied.

## Safety Rules

- Always close Calibre before running `calibredb`.
- Always keep recent backups of `metadata.db` and `metadata_db_prefs_backup.json`.
- Never apply changes without a clean dry run.
- Do not invent unsupported LCC values merely to complete a field.
- Do not assign ISBNs from other editions just to force matching.
- Treat no-ISBN books as manual-review or CalibreId-match candidates.

## Batch File Types

### Source TSV

The source TSV is exported from Calibre and sent for LCC enrichment.

Typical file name:

```text
input/lcc-source-{batch}.tsv
```

It usually includes:

- CalibreId
- Title
- Author(s)
- ISBN
- Publisher
- Published
- Existing LCC fields

### Import TSV

The import TSV contains proposed LCC values to be tested and applied.

Typical file name:

```text
input/lcc-import-{batch}.tsv
```

Required columns:

| Column | Purpose |
|---|---|
| `Title` | Human-readable title reference |
| `Author` | Human-readable author reference |
| `ISBN` | Current primary match key |
| `LCC` | Proposed raw LCC call number |
| `LCC Primary Class` | Proposed canonical primary class |
| `LCC Secondary Class` | Proposed canonical secondary class |
| `LCC Classification Path` | Proposed human-readable classification path |

## Reports

The toolkit should produce reports in the `reports` folder.

Typical files:

```text
reports/lcc-dryrun-{batch}.csv
reports/lcc-apply-{batch}.csv
reports/lcc-verify-{batch}.csv
reports/lcc-summary-{batch}.txt
```

### Dry Run Report

The dry run report shows what would change without modifying Calibre.

Important fields include:

- MatchStatus
- CalibreId
- ExistingLCC
- ProposedLCC
- WouldUpdateLCC
- ExistingLCCPrimaryClass
- ProposedLCCPrimaryClass
- WouldUpdateLCCPrimaryClass
- ExistingLCCSecondaryClass
- ProposedLCCSecondaryClass
- WouldUpdateLCCSecondaryClass
- ExistingLCCPath
- ProposedLCCPath
- WouldUpdateLCCPath
- Warning

### Apply Report

The apply report shows what was actually updated.

### Verify Report

The verify report is a post-apply dry run against the same import TSV.

A clean verify means every `WouldUpdate...` field says:

```text
No
```

## Expected Clean Verification

A completed batch should show:

```text
WouldUpdateLCC               No
WouldUpdateLCCPrimaryClass   No
WouldUpdateLCCSecondaryClass No
WouldUpdateLCCPath           No
```

For every row in the batch.

## Matching Rules

Current v0.1/v0.2 matching is primarily ISBN-based.

Known limitation:

- Older books without ISBN may require manual handling.
- Future versions should support CalibreId-first matching with ISBN fallback.

Preferred future matching order:

1. CalibreId
2. ISBN
3. Manual review

## Exact Award Program Filtering

Some Calibre searches against multi-value award fields may overmatch.

Example issue:

```text
#award_programs:"AHA - Herbert Baxter Adams Prize"
```

may return broader results than expected.

For award batches, the toolkit should support exact local filtering against the actual `Award Programs` field so that only records with the exact award program value are exported.

## Canonical Dropdown Rules

### LCC Primary Class

Format:

```text
<Letter> - <Top-Level LCC Class>
```

Example:

```text
H - Social Sciences
```

### LCC Secondary Class

Format:

```text
<Code or Range> - <Subclass Caption>
```

Example:

```text
HD - Industries / Land Use / Labor
```

Rules:

- Use compact values.
- Do not repeat the primary class family.
- Use spaced slashes.
- Do not use commas inside dropdown values.
- Use canonical values from `config/lcc-secondary-canonical.csv`.

## Manual MQG Completion

The toolkit does not automatically mark `MQG-08: LCC` complete.

Reason:

- Final MQG completion should remain a human review step.
- The user should review selected records manually in Calibre before marking the gate complete.

## Version Notes

### v0.1

Initial working script set:

- `Export-CalibreBatchForLcc.ps1`
- `Test-LccImportDryRun.ps1`
- `Invoke-LccImportApply.ps1`

Validated successfully against the AHA Herbert Baxter Adams Prize batch.

### v0.2 Goals

- Add central config.
- Add canonical Primary and Secondary Class files.
- Add import canonicalization.
- Add health checks.
- Add batch summary reports.
- Add safer apply confirmation requiring `APPLY`.
- Add menu launcher.

## Current Folder Structure

```text
lcc-toolkit/
├─ config/
├─ docs/
├─ input/
├─ reports/
├─ scripts/
├─ .gitattributes
├─ .gitignore
└─ Start-LccWorkflow.ps1
```

## Common Commands

### Run Dry Run

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Test-LccImportDryRun.ps1 `
  -InputTsv ".\input\lcc-import-{batch}.tsv" `
  -ReportCsv ".\reports\lcc-dryrun-{batch}.csv"
```

### Apply Verified Import

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Invoke-LccImportApply.ps1 `
  -DryRunReportCsv ".\reports\lcc-dryrun-{batch}.csv" `
  -ApplyReportCsv ".\reports\lcc-apply-{batch}.csv" `
  -Apply
```

### Verify Final State

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Test-LccImportDryRun.ps1 `
  -InputTsv ".\input\lcc-import-{batch}.tsv" `
  -ReportCsv ".\reports\lcc-verify-{batch}.csv"
```

### Check Verification Summary

```powershell
Import-Csv ".\reports\lcc-verify-{batch}.csv" |
  Select-Object InputTitle, ISBN,
    WouldUpdateLCC,
    WouldUpdateLCCPrimaryClass,
    WouldUpdateLCCSecondaryClass,
    WouldUpdateLCCPath |
  Format-Table -AutoSize
```

## Recovery Guidance

If something looks wrong:

1. Stop.
2. Do not rerun apply repeatedly.
3. Review the dry-run and apply reports.
4. Confirm Calibre is closed.
5. Confirm the import TSV uses canonical dropdown values.
6. Restore from backup if needed.
7. Re-run dry run before applying again.