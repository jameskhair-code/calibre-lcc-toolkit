# Productive Launcher and Target Selection - v0.12.0 Design

## Purpose

This document defines the next operator-experience direction for the Calibre Metadata Toolkit.

The toolkit has reached a stable technical foundation through v0.11.0. The next major need is not more script sprawl. The next major need is a simplified productive-use launcher that exposes meaningful metadata actions instead of internal pipeline mechanics.

The goal is to make the tool something the user can use often.

## Core Principle

Expose decisions and actions, not mechanics.

The main launcher should not expose routine internal steps such as export, diagnostics, validation, preflight, report viewing, health checks, or status checks unless those steps are needed for review, approval, troubleshooting, or recovery.

Internal scripts and reports can still exist. They should be hidden from the normal operator path.

## Productive Launcher Vision

The main launcher should be intentionally minimal.

Proposed top-level menu:

Calibre Metadata Toolkit

What do you want to work on?

1. MQG-01: Clean Title & Author
2. MQG-02: Fix / Confirm Identifiers
3. MQG-03: Add LCC Classification
4. MQG-05: Build Comments
5. MQG-06: Build Tags

A. Advanced Tools
0. Exit

## Active MQG Scope

Active workflows:

| MQG | Label | Tool Role |
|---|---|---|
| MQG-01 | Title & Author | Guided cleanup workflow |
| MQG-02 | Identifiers | Guided identifier confirmation and future proposal workflow |
| MQG-03 | LCC | Guided classification workflow |
| MQG-05 | Description / Comments | AI-assisted comments workflow |
| MQG-06 | Tags | AI/rules-assisted tag workflow |

Parked or manual workflows:

| MQG | Status | Reason |
|---|---|---|
| MQG-04 Awards | Parked / deprecated as standalone workflow | Awards may later be handled inside Comments or a future v2 structured awards model |
| MQG-07 Cover | Manual only | Cover work does not need this PowerShell tool |
| MQG-99 Metadata Complete | Manual final gate | User expects to mark final completeness manually in Calibre |

## Target Selection Principle

Every productive MQG workflow should begin by asking:

Which books should be processed?

Target selection is the real first step of productive work.

The tool should support three first-class target modes:

1. Paste a Calibre search string.
2. Process all books missing the selected MQG.
3. Use an existing batch manifest.

This supports both current backlog processing and future maintenance or catch-up workflows.

## Target Selection Menu

Each MQG workflow should start with a shared selector:

Which books should be processed?

1. Paste Calibre search string
2. All books where this MQG is not complete
3. Use existing batch manifest
0. Back

## Mode 1 - Paste Calibre Search String

The user may provide a Calibre search string that defines the target set for the run.

Example:

#collection:"=North American Colonial & Early National Studies" and not #mqg_tags:true

The tool should use the search string to create or refresh the working batch for that workflow.

## Mode 2 - All Books Missing This MQG

The tool should use the MQG-specific incomplete-field rule to select backlog items.

Conceptual examples:

| Workflow | Backlog selector concept |
|---|---|
| MQG-01 Title & Author | all records where #mqg_title_author is not complete |
| MQG-02 Identifiers | all records where #mqg_identifiers is not complete |
| MQG-03 LCC | all records where #mqg_lcc is not complete |
| MQG-05 Description / Comments | all records where #mqg_description is not complete |
| MQG-06 Tags | all records where #mqg_tags is not complete |

The exact Calibre search syntax must be verified before implementation.

## Mode 3 - Existing Batch Manifest

The tool should allow the operator to reuse a previously generated batch manifest.

This supports repeatable runs, recovery, and controlled follow-up processing.

## Backlog Mode and Maintenance Mode

The target-selection model must support two lifecycle phases.

Backlog mode:

- A large portion of the library still needs processing.
- The user may need to process hundreds or thousands of records over time.
- The tool should support processing all entries missing a selected MQG.
- The tool should show a count before proceeding.
- The tool should support limiting to the first N records.
- The tool should support batch chunking.

Maintenance mode:

- Most of the library will eventually be processed.
- The user will mostly catch strays, new additions, or new award-year batches.
- The tool should support pasted search strings, recent additions, all remaining incomplete records, and existing manifests.

## Count Before Continue

Any target-selection mode that may produce many records should show the count before proceeding.

Example:

Target selection found 3,842 books missing MQG-06 Tags.

Options:

1. Continue with all 3,842
2. Limit to first N books
3. Save batch only
4. Cancel

This is especially important for AI-heavy workflows such as Comments and Tags.

## Hidden Report Philosophy

Reports remain important, but they should not dominate the main menu.

Reports should exist for:

1. tool state,
2. AI input,
3. audit trail,
4. review and approval,
5. troubleshooting.

Reports should be shown to the user only when they support a decision.

Examples:

| Internal artifact | User-facing decision |
|---|---|
| diagnostics CSV | I found 958 Identifier records needing review. |
| proposal worksheet | Open proposed changes for review? |
| validation report | 203 updates are safe; 11 need manual review. |
| preflight report | These records are safe to mark complete. |
| verify report | Apply succeeded: 124 updated, 0 failed. |

## Advanced Tools

The existing script-level menu should not be removed. It should move behind an Advanced Tools entry.

Advanced Tools may include:

- legacy LCC workflow options,
- Author/Title export, dry-run, apply, verify steps,
- Identifier inventory, diagnostics, proposal, validation, preflight, apply steps,
- Comments export, dry-run, review, apply, verify steps,
- manual MQG completion tools,
- report folder access,
- health check,
- Git status,
- developer and recovery utilities.

Advanced Tools are for debugging, recovery, development, and unusual cases.

They are not the default productive experience.

## Productive MQG Workflow Shape

Each active MQG should eventually follow this shape:

1. Select MQG workflow.
2. Select target books.
3. Tool creates or refreshes working batch.
4. Tool runs hidden internal steps as needed.
5. Tool presents a decision:
   - review proposals,
   - apply approved changes,
   - mark safe records complete,
   - stop for manual review.
6. Tool applies only after explicit confirmation where writes are involved.
7. Tool verifies with Calibre readback where practical.
8. Tool produces an audit artifact.
9. Tool returns a useful summary.

## MQG-01 Productive Workflow

Goal: Clean Title & Author.

Expected guided behavior:

- select target books,
- export source data if needed,
- generate or dry-run cleanup proposal,
- show proposed changes,
- apply approved changes,
- verify,
- mark MQG-01 complete where safe.

The user should not need to manually choose A1 through A6 for normal use.

## MQG-02 Productive Workflow

Goal: Fix / Confirm Identifiers.

Current validated capability:

- inventory,
- diagnostics,
- proposal worksheet,
- validation,
- preflight,
- apply MQG-02 complete for preflight-approved rows,
- readback verification.

Future productive behavior:

- select target books,
- confirm already-good records,
- identify missing or suspicious identifiers,
- generate AI/search-assisted proposals where possible,
- review proposed ISBN, Amazon, and Goodreads updates,
- apply approved updates,
- mark MQG-02 complete where safe.

Important boundary:

AI may propose identifier updates. AI should not silently mark identifier updates complete without review and evidence.

## MQG-03 Productive Workflow

Goal: Add LCC Classification.

Expected guided behavior:

- select target books,
- export LCC candidates,
- prepare or canonicalize LCC import data,
- validate,
- apply approved LCC metadata,
- verify,
- mark MQG-03 complete where safe.

The LCC workflow should remain central but should no longer dominate the top-level launcher identity.

## MQG-05 Productive Workflow

Goal: Build Comments.

Expected guided behavior:

- select target books,
- generate comments using the current comments template and ruleset,
- create review artifact,
- allow user review and approval,
- apply approved comments,
- verify,
- mark MQG-05 complete where safe.

This is a high-value AI-assisted workflow and may eventually absorb useful awards or reception information.

## MQG-06 Productive Workflow

Goal: Build Tags.

Expected guided behavior:

- select target books,
- export current tags,
- compare against a controlled vocabulary and ruleset,
- generate tag proposals,
- validate proposals against rules,
- allow review,
- apply approved tags,
- verify,
- mark MQG-06 complete where safe.

A tag ruleset should be designed before heavy implementation.

## Naming Direction

The visible product identity should become:

Calibre Metadata Toolkit

Historical implementation names may remain temporarily:

- repo: calibre-lcc-toolkit,
- folder: lcc-toolkit,
- launcher: Start-LccWorkflow.ps1.

This should be treated as a compatibility state, not the final product identity.

## v0.12.0 Recommended Scope

Recommended v0.12.0 scope:

1. Capture this design document.
2. Capture a project identity and rename decision.
3. Optionally create or refresh a lightweight primary README or orientation document.
4. Do not yet rewrite the launcher unless the design is accepted.
5. Do not add new AI metadata behavior yet.
6. Do not expand Comments or Tags implementation yet.

## Future Implementation Sequence

Potential sequence after design acceptance:

1. v0.12.1 - Productive Launcher Shell
2. v0.12.2 - Shared Target Selection Helper
3. v0.12.3 - MQG-01 Guided Title & Author Workflow
4. v0.12.4 - MQG-03 Guided LCC Workflow
5. v0.13.0 - MQG-02 Identifier Proposal Engine Design
6. v0.14.0 - MQG-05 Comments Builder Workflow
7. v0.15.0 - MQG-06 Tags Ruleset and Proposal Workflow

## Status

Status: Draft design for v0.12.0.

Next action:

Review this design, then create the project identity and rename decision document.
