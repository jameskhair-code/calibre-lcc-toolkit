# Calibre LCC Toolkit Workflow

This document describes the operating workflow for the Calibre LCC Toolkit.

The toolkit is designed to make Library of Congress Classification (LCC) enrichment repeatable, reviewable, and safe for a Calibre library.

The current workflow is organized into seven phases:

```text
Preflight -> Export -> Enrich -> Prepare -> Validate -> Apply -> Verify
```

The launcher menu directly reflects these phases:

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
10. Show Git status
0. Exit
```

---

## Purpose

The Calibre LCC Toolkit helps populate and verify these Calibre fields:

| Field | Purpose |
|---|---|
| `LCC` | Raw Library of Congress Classification call number |
| `LCC Primary Class` | Top-level LCC class |
| `LCC Secondary Class` | Controlled subclass dropdown value |
| `LCC Classification Path` | Human-readable browsing path |

The toolkit separates research, validation, and application so metadata changes can be reviewed before they are written to Calibre.

---

## Safety Model

Most phases are read-only.

| Phase | Modifies Calibre? |
|---|---|
| Preflight | No |
| Export | No |
| Enrich | No |
| Prepare | No |
| Validate | No |
| Apply | Yes |
| Verify | No |

The **Apply** phase is the only normal workflow phase that writes metadata to Calibre.

Apply requires two confirmations:

1. The launcher asks for `YES`.
2. The apply script asks for `APPLY` when pending updates exist.

This is intentional.

---

## Phase 1 - Preflight

Menu option:

```text
1. Preflight: Run toolkit health check
```

Purpose:

Confirm that the toolkit environment is ready.

The health check validates:

- Toolkit root
- Config file
- Input folder
- Reports folder
- Scripts folder
- Docs folder
- `calibredb.exe`
- Primary canonical CSV
- Secondary canonical CSV
- Required scripts
- Whether Calibre appears to be running

Preferred result:

```text
Status: HEALTHY
```

Acceptable but cautious result:

```text
Status: HEALTHY WITH WARNINGS
```

Example warning:

```text
Calibre-related process detected
```

If Calibre is running, close it before exporting or applying metadata.

---

## Phase 2 - Export

Menu option:

```text
2. Export: Create source TSV from Calibre
```

Purpose:

Read selected records from Calibre and create a source TSV for LCC enrichment.

This phase does not modify Calibre metadata.

Input:

- Batch file slug
- Calibre search string
- Optional exact Award Programs filter
- Output source TSV path
- Optional Calibre library path

Example batch file slug:

```text
j-russell-major-prize
```

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

### Batch File Slug

The batch file slug is only used for default filenames.

It does not need to match a Calibre field.

Good examples:

```text
j-russell-major-prize
herbert-baxter-adams
marraro-prize
aha-gershoy
```

### Exact Award Programs Filter

Award fields may overmatch when searched through Calibre or `calibredb`.

For award batches, use a loose Calibre search to get candidates, then use the exact Award Programs filter to narrow the exported source file.

Example:

```text
Calibre search string:
#award_programs:"AHA - J. Russell Major Prize" and #mqg_lcc:false

Exact Award Programs filter:
AHA - J. Russell Major Prize
```

The export script first retrieves candidate records, then locally filters the actual `Award Programs` field for an exact match.

---

## Phase 3 - Enrich

This is the manual or ChatGPT-assisted research phase.

There is no launcher menu option for Enrich because the toolkit itself does not research LCC data automatically.

Input:

```text
input/lcc-source-{batch}.tsv
```

Output:

```text
input/lcc-import-{batch}.tsv
```

The completed import TSV should contain:

```text
Title
Author
ISBN
LCC
LCC Primary Class
LCC Secondary Class
LCC Classification Path
```

Example:

```text
input/lcc-import-j-russell-major-prize.tsv
```

The enrichment phase should follow the methodology described in:

```text
docs/LCC-Methodology.md
```

---

## Phase 4 - Prepare

Menu option:

```text
3. Prepare: Canonicalize completed LCC import TSV
```

Purpose:

Normalize the completed import TSV against the approved Calibre dropdown values.

This phase does not modify Calibre metadata.

Input:

```text
input/lcc-import-{batch}.tsv
```

Output:

```text
input/lcc-import-{batch}-canonical.tsv
```

Report:

```text
reports/lcc-canonicalize-{batch}.csv
```

Example:

```text
input/lcc-import-j-russell-major-prize.tsv
input/lcc-import-j-russell-major-prize-canonical.tsv
reports/lcc-canonicalize-j-russell-major-prize.csv
```

The canonicalization step maps values using:

```text
config/lcc-primary-canonical.csv
config/lcc-secondary-canonical.csv
```

A clean result should show:

```text
Warnings: 0
```

If warnings appear, review and fix the canonical mappings or import TSV before continuing.

---

## Phase 5 - Validate

Menu option:

```text
4. Validate: Dry run import and write summary
```

Purpose:

Compare the canonical import TSV to the current Calibre records and show what would change.

This phase does not modify Calibre metadata.

Input:

```text
input/lcc-import-{batch}-canonical.tsv
```

Dry-run report:

```text
reports/lcc-dryrun-{batch}.csv
```

Dry-run summary:

```text
reports/lcc-summary-{batch}-dryrun.txt
```

A good dry-run result before applying usually looks like:

```text
Rows: 24
Matched: 24
Pending field updates: 94
Warnings: 0
Status: READY TO APPLY
```

Before applying, review:

- Row count
- Matched count
- Warning count
- Pending field updates
- Any unexpected LCC values
- Any records known to have weaker catalog evidence

Do not apply if:

- Any rows are unmatched.
- Any warnings require review.
- The row count is not what you expected.
- The source/import batch appears mixed or overmatched.

---

## Phase 6 - Apply

Menu option:

```text
5. Apply: Write approved LCC metadata to Calibre
```

Purpose:

Write approved LCC metadata to Calibre.

This is the only normal workflow phase that modifies Calibre metadata.

Before applying:

1. Close Calibre.
2. Confirm the dry-run summary says `READY TO APPLY`.
3. Confirm matched row count is expected.
4. Confirm warnings are zero.
5. Confirm you are using the correct dry-run report.

The launcher asks:

```text
Continue to apply script? Type YES to continue
```

Type:

```text
YES
```

Then the apply script shows a preflight summary and asks:

```text
Confirmation:
```

Type:

```text
APPLY
```

The apply report is written to:

```text
reports/lcc-apply-{batch}.csv
```

---

## Phase 7 - Verify

Menu option:

```text
6. Verify: Confirm final state and write summary
```

Purpose:

Confirm that Calibre now matches the canonical import TSV.

This phase does not modify Calibre metadata.

Input:

```text
input/lcc-import-{batch}-canonical.tsv
```

Verify report:

```text
reports/lcc-verify-{batch}.csv
```

Verify summary:

```text
reports/lcc-summary-{batch}-verify.txt
```

Final win condition:

```text
Rows: 24
Matched: 24
Pending field updates: 0
Warnings: 0
Status: VERIFIED CLEAN
```

After this, manually inspect selected records in Calibre before marking MQG complete.

---

## File Lifecycle

For a batch named:

```text
j-russell-major-prize
```

Expected files are:

| Phase | File |
|---|---|
| Export | `input/lcc-source-j-russell-major-prize.tsv` |
| Enrich | `input/lcc-import-j-russell-major-prize.tsv` |
| Prepare | `input/lcc-import-j-russell-major-prize-canonical.tsv` |
| Prepare Report | `reports/lcc-canonicalize-j-russell-major-prize.csv` |
| Validate Report | `reports/lcc-dryrun-j-russell-major-prize.csv` |
| Validate Summary | `reports/lcc-summary-j-russell-major-prize-dryrun.txt` |
| Apply Report | `reports/lcc-apply-j-russell-major-prize.csv` |
| Verify Report | `reports/lcc-verify-j-russell-major-prize.csv` |
| Verify Summary | `reports/lcc-summary-j-russell-major-prize-verify.txt` |

Generated `input` and `reports` files are ignored by Git by default.

---

## Common Commands

### Start the launcher

```powershell
powershell -ExecutionPolicy Bypass -File .\Start-LccWorkflow.ps1
```

### Check Git status

```powershell
git status
git log --oneline --decorate --max-count 12
```

### Check for Calibre processes

```powershell
Get-Process calibre* -ErrorAction SilentlyContinue
```

### Open documentation

```powershell
notepad++ ".\README.md"
notepad++ ".\docs\LCC-Toolkit-Workflow.md"
notepad++ ".\docs\LCC-Methodology.md"
```

---

## Manual MQG Completion

The toolkit does not automatically mark `MQG-08: LCC` complete.

Reason:

- MQG completion should remain a human review step.
- The user should review selected records manually in Calibre.
- Some records may require confidence review even if the technical import succeeded.

Recommended final manual process:

1. Run Verify.
2. Confirm `VERIFIED CLEAN`.
3. Open Calibre.
4. Spot-check selected records.
5. Review any known weak-confidence records.
6. Manually mark `MQG-08: LCC` complete.

---

## Troubleshooting

### Export returns too many rows

Use the exact Award Programs filter.

### Export returns zero rows

Try a looser Calibre search string. Avoid exact `=` award searches if they return zero rows through `calibredb`.

### Calibre lock error

Close Calibre and rerun the step.

### Canonicalization warnings

Review:

```text
reports/lcc-canonicalize-{batch}.csv
```

Then update either:

- the import TSV, or
- the canonical mapping CSVs.

### Dry run has unmatched rows

Do not apply.

Check ISBNs, titles, source batch, and import TSV alignment.

### Apply fails

Stop and review:

```text
reports/lcc-apply-{batch}.csv
```

Do not repeatedly rerun apply without understanding the issue.

### Verify is not clean

Do not mark MQG complete.

Review:

```text
reports/lcc-verify-{batch}.csv
reports/lcc-summary-{batch}-verify.txt
```

---

## Version Notes

### v0.1

Initial working script baseline.

### v0.2

Accepted toolkit baseline with:

- interactive launcher
- health check
- canonicalization
- exact Award Programs filtering
- dry run
- apply safety
- verification
- summary reports

### v0.3

Workflow and documentation polish:

- phase-based launcher labels
- Validate combines dry run + summary
- Verify combines final check + summary
- README added
- methodology documentation added
- workflow documentation updated

---

## Practical Rule

If the workflow becomes confusing, return to the phase model:

```text
Preflight -> Export -> Enrich -> Prepare -> Validate -> Apply -> Verify
```

Only **Apply** writes to Calibre.

Everything before Apply is preparation and validation.

Everything after Apply is verification.
