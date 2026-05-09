# Calibre Metadata Toolkit - Project Roadmap

## 1. Purpose

This repository began as the Calibre LCC Toolkit, focused on safe Library of Congress Classification enrichment and import workflows.

Beginning with the v0.5 development cycle, the broader project identity is:

**Calibre Metadata Toolkit**

The existing LCC workflow remains the first stable module. Future development will add additional metadata cleanup and enrichment modules while preserving the same core operating model:

- export first
- enrich externally when useful
- dry run before apply
- report every proposed change
- require explicit confirmation before metadata writes
- verify after apply

The goal is not to create a magic one-click metadata machine. The goal is to create a practical, modular, reviewable toolkit that helps improve a Calibre library safely and repeatably.

## 2. Current Stable State

Current stable branch:

```text
main
```

Current stable tag:

```text
v0.8.4
```

Current repository name:

```text
calibre-lcc-toolkit
```

Current broader project identity:

```text
Calibre Metadata Toolkit
```

The repository name should not be changed yet. The project should prove at least one successful non-LCC module before considering a GitHub repository rename.

## 3. Current Stable Module: LCC

The current LCC module supports the following workflow:

```text
Preflight -> Export -> Enrich -> Prepare -> Validate -> Apply -> Verify
```

Current launcher:

```text
Start-LccWorkflow.ps1
```

Major scripts:

```text
scripts/Export-CalibreBatchForLcc.ps1
scripts/Convert-LccImportToCanonical.ps1
scripts/Test-LccImportDryRun.ps1
scripts/Write-LccBatchSummary.ps1
scripts/Invoke-LccImportApply.ps1
scripts/Test-LccToolkitHealth.ps1
scripts/Show-LccLatestReports.ps1
```

Current LCC capabilities include:

- latest reports viewer
- launcher option for latest reports
- toolkit health check
- optional LCC enrichment audit fields
- confidence tracking
- source notes tracking
- canonical import preparation
- dry-run validation
- summary reporting
- apply-time blocking for unsafe rows
- verification workflow
- supporting documentation

Allowed LCC confidence values:

```text
High - Catalog Confirmed
Medium - Evidence Based
Low - Manual Review Recommended
```

The LCC module should remain stable while new modules are developed around it.

## 4. Core Design Principles

These rules apply to every module in the toolkit.

### 4.1 Dry Run Before Write

Every metadata-changing operation must have a dry run.

No apply script should be introduced without a corresponding dry-run workflow.

### 4.2 Report Every Change

Every module should produce a reviewable report.

Reports should show:

- target Calibre record
- original value
- proposed value
- change reason
- confidence
- manual review status
- blocking issues, when present

### 4.3 Explicit Apply Confirmation

Apply scripts must require explicit confirmation before writing metadata.

The toolkit should never silently modify Calibre metadata.

### 4.4 Prefer CalibreId for High-Risk Writes

For high-risk fields such as title, author, and comments, workflows should use `CalibreId` wherever possible.

ISBN can help identify books, but `CalibreId` should be the preferred write target when modifying existing records.

### 4.5 TSV First, Calibre Columns Later

Audit and provenance fields should begin in TSV and report workflows before adding new Calibre custom columns.

This keeps the library schema from growing too quickly and allows the workflow to mature first.

### 4.6 Boring Is Good

The toolkit should favor predictable scripts, plain TSV files, readable reports, and small module boundaries.

Avoid clever automation when a safer review step would be better.

## 5. Safety Model

The toolkit uses a layered safety model.

### 5.1 Read-Only Operations

Read-only operations may include:

- health checks
- exports
- report viewing
- source TSV generation
- dry-run comparison
- validation reports

Read-only operations must not modify Calibre metadata.

### 5.2 Write Operations

Write operations may include:

- applying LCC values
- applying title changes
- applying author changes
- applying comments HTML
- applying identifiers
- applying future metadata fields

Write operations must:

- use a prepared/canonical input file
- require a prior clean dry run
- block rows marked for manual review
- block unexpected confidence values
- require explicit user confirmation
- produce a post-apply verification report when practical

### 5.3 Blocking Conditions

Modules should block apply when:

- `ManualReviewRequired = Yes`
- confidence value is unexpected
- required fields are missing
- proposed value is blank for a non-blank original field, unless explicitly allowed
- target `CalibreId` cannot be found
- proposed change does not match the dry-run expectation
- duplicate or ambiguous targets are detected

## 6. Planned Modules

### 6.1 LCC Module

Purpose:

Improve Library of Congress Classification metadata for selected Calibre records.

Status:

Stable.

Primary workflow:

```text
Preflight -> Export -> Enrich -> Prepare -> Validate -> Apply -> Verify
```

Future LCC improvements may include:

- better batch history tracking
- richer source/provenance reports
- optional LOC link support
- improved launcher integration after multi-module architecture exists

### 6.2 Author / Title Cleanup Module

Purpose:

Safely clean title and author metadata before downstream enrichment.

This module should help normalize records where title or author formatting reduces metadata lookup quality.

Initial scope should remain narrow:

- export candidate records
- accept proposed title/author cleanup TSV
- dry run proposed changes
- summarize changes
- apply only after confirmation
- verify final state

The first version should not attempt to fully auto-generate all proposed title/author changes. External review and ChatGPT-assisted TSV preparation are acceptable.

### 6.3 Comments Field Generation Module

Purpose:

Generate and apply structured HTML comments for selected Calibre records.

Expected future workflow:

```text
Export -> Generate Proposed Comments -> Dry Run -> Summary -> Apply -> Verify
```

This module should be treated as high-risk because comments may contain rich HTML and long-form descriptive content.

Design docs should come before implementation:

```text
docs/Comments-Field-Workflow.md
docs/Comments-Template-Standard.md
```

### 6.4 Award Metadata Cleanup Module

Purpose:

Support cleanup and normalization of award-related metadata.

Potential future targets:

- award program
- award name
- award entry
- year
- status
- category

This should remain deferred until the author/title and comments modules are stable.

### 6.5 Identifier / LOC Catalog Link Module

Purpose:

Explore whether LOC catalog links and other provenance identifiers should be stored in Calibre identifiers, comments, source notes, or custom fields.

Open questions:

- Can Calibre custom identifiers be made clickable?
- Which LOC URL format is stable enough?
- Should LOC links be stored only for high-confidence records?
- Should LOC links live in identifiers, comments, source notes, or a custom field?
- Should this module be part of LCC enrichment or a separate provenance module?

### 6.6 MQG / Quality Gate Reporting Module

Purpose:

Create reports that support the broader Metadata Quality Gate workflow.

Potential reports:

- records missing LCC
- records missing usable comments
- records with low tag counts
- records with title/author cleanup candidates
- records with weak or incomplete identifiers
- records with incomplete custom fields

This should initially remain report-only.

### 6.7 Review Packet Module

Purpose:

Produce human-friendly review packets from one or more metadata modules.

Potential packet types:

- owner/reviewer packets
- batch cleanup packets
- before/after reports
- module progress reports
- library quality dashboards

This is a future reporting layer and should not be implemented until multiple modules exist.

## 7. Version Roadmap

### v0.5 - Author / Title Cleanup

Recommended branch:

```text
v0.5-author-title-cleanup
```

Goal:

Create a safe dry-run/apply workflow for author and title cleanup.

Initial scope:

- export records for cleanup review
- accept proposed cleanup TSV
- dry run title/author changes
- produce summary report
- apply approved changes after explicit confirmation
- verify final values after apply

Possible input fields:

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

Allowed confidence values:

```text
High - Mechanical Cleanup
Medium - Evidence Based
Low - Manual Review Recommended
```

Expected v0.5 docs:

```text
docs/Author-Title-Cleanup-Workflow.md
```

Possible v0.5 scripts:

```text
scripts/Export-CalibreBatchForAuthorTitleCleanup.ps1
scripts/Test-AuthorTitleCleanupDryRun.ps1
scripts/Write-AuthorTitleCleanupSummary.ps1
scripts/Invoke-AuthorTitleCleanupApply.ps1
scripts/Test-AuthorTitleCleanupVerify.ps1
```

Implementation note:

The dry-run/report path should be completed before the apply script is added.

### v0.6 - Structured Comments Module

Goal:

Create a safe workflow for generating and applying structured HTML comments.

Expected design docs:

```text
docs/Comments-Field-Workflow.md
docs/Comments-Template-Standard.md
```

Initial scope:

- export source records
- accept proposed comments HTML
- dry run comments changes
- summarize existing vs proposed comments
- apply after confirmation
- verify final comments state

Possible fields:

```text
CalibreId
Title
Authors
ExistingComments
ProposedComments
ChangeReason
Confidence
ManualReviewRequired
SourceNotes
```

Comments should be treated as high-risk because they may overwrite substantial existing metadata.

### v0.9 - LOC Identifier / Provenance Support

Goal:

Explore and prototype LOC catalog link and provenance support.

Initial scope should be research and proof-of-concept only.

Questions to answer:

- where should LOC links live?
- what URL pattern is durable?
- can custom identifiers be clickable in Calibre?
- should links be stored only when LCC confidence is high?
- should LOC source notes feed into the Comments module?

Possible outputs:

```text
docs/LOC-Identifier-Provenance-Research.md
docs/Identifier-Storage-Options.md
```

## 8. Deferred Ideas

The following ideas are useful but should remain deferred:

- full automatic title cleanup
- full automatic author cleanup
- automatic web lookup of canonical metadata
- automatic Goodreads/Amazon reconciliation
- award metadata normalization
- advanced MQG dashboards
- GUI wrapper
- repo rename
- full plugin packaging
- direct Calibre database writes outside `calibredb`
- automatic comments generation without human review

## 9. Repository Naming Strategy

Current GitHub repo:

```text
calibre-lcc-toolkit
```

Preferred broader project name:

```text
Calibre Metadata Toolkit
```

Do not rename the GitHub repository yet.

Recommended approach:

1. Keep current repo name through v0.7.1.
2. Continue using broader project language in README/docs.
3. Consider a future repo rename only after the multi-module toolkit shape is stable.
4. Revisit repo naming only after the multi-module toolkit shape is stable.
5. Rename only if the broader toolkit identity is clearly established.

Possible future repo names:

```text
calibre-metadata-toolkit
calibre-metadata-ops
calibre-library-toolkit
```

Preferred likely future name:

```text
calibre-metadata-toolkit
```

## 10. Future Module Design Rules

Every future module should define:

- purpose
- read-only operations
- write operations
- input TSV schema
- output report schema
- confidence values
- manual review behavior
- blocking conditions
- apply confirmation behavior
- verification behavior
- launcher integration
- documentation requirements

Every module should have at least:

```text
Export
Dry Run
Summary
Apply
Verify
Documentation
```

Apply may be deferred until export/dry-run/summary are stable.

## 11. Launcher Direction

The current launcher is LCC-specific:

```text
Start-LccWorkflow.ps1
```

Do not immediately replace it.

Possible future launcher structure:

```text
Start-CalibreMetadataToolkit.ps1
```

Possible future menu:

```text
1. LCC Workflow
2. Author / Title Cleanup
3. Comments Workflow
4. Identifier / Provenance Workflow
5. Reports
6. Health Check
0. Exit
```

Recommended approach:

- keep `Start-LccWorkflow.ps1` stable for now
- add module-specific scripts first
- introduce a broader launcher after at least two modules exist
- avoid breaking the existing LCC workflow

## 12. Immediate Next Steps

Current development branch:

```text
v0.8.4-lcc-mqg-complete
```

Recommended next work:

1. Finish README and roadmap polish.
2. Run full PowerShell parser check.
3. Review git diff.
4. Commit v0.7.1 documentation polish.
5. Merge into main.
6. Tag v0.7.1.
7. Push main, branch, and tag.

## 13. Operating Reminder

This toolkit should remain safe enough that future-you trusts it after six months away from the project.

When in doubt:

```text
Export first.
Dry run first.
Report first.
Apply last.
Verify always.
```

### v0.8.3 - MQG Order Alignment

Added `docs/MQG-Workflow-Architecture.md` to define the canonical one-pass MQG processing order.

Clarified that Calibre display labels may be reordered while stable lookup names should remain unchanged.

Canonical MQG order:

    MQG-01: Title & Author
    MQG-02: Identifiers
    MQG-03: LCC
    MQG-04: Awards
    MQG-05: Description / Comments
    MQG-06: Tags
    MQG-07: Cover
    MQG-99: Metadata Complete

### v0.8.4 - LCC Verified MQG Completion

Added LCC MQG completion support.

The LCC gate now follows the verified-completion pattern:

    LCC verify report
    -> eligible rows only
    -> mark #mqg_lcc true
    -> read back confirmation

MQG-03: LCC requires all four LCC fields to be populated and verified:

    LCC
    LCC Classification Path
    LCC Primary Class
    LCC Secondary Class

The script also detects already-complete rows and reports them without rewriting the checkbox.

