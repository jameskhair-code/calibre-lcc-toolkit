# Calibre Metadata Toolkit - Orientation

## What This Tool Is

The Calibre Metadata Toolkit is a PowerShell-based workflow system for improving and maintaining metadata quality in a Calibre library.

The project began as a Library of Congress Classification helper, historically implemented as `calibre-lcc-toolkit`, but it has expanded into a broader metadata workflow toolkit.

The visible product identity is now:

Calibre Metadata Toolkit

The historical repo, folder, and launcher names may remain temporarily for compatibility.

## What Problem It Solves

The toolkit is intended to make Calibre metadata cleanup:

- repeatable,
- safe,
- reviewable,
- auditable,
- guided,
- practical for large backlogs,
- practical for small future maintenance batches.

It is not meant to replace human judgment. It is meant to reduce repetitive metadata labor and make review/apply workflows safer.

## Current Product Direction

The project is moving away from a script-list launcher and toward a productive MQG workflow launcher.

The desired normal experience is:

1. Choose the metadata area to work on.
2. Choose the books to process.
3. Let the tool run internal checks and generate needed artifacts.
4. Review proposed changes when needed.
5. Apply approved changes only after explicit confirmation.
6. Verify results.
7. Mark the relevant MQG complete only when evidence exists.

## Active MQG Workflows

The active productive workflows are:

| MQG | Workflow | Purpose |
|---|---|---|
| MQG-01 | Title & Author | Clean and standardize title/author metadata |
| MQG-02 | Identifiers | Confirm, repair, and eventually enrich ISBN/Amazon/Goodreads identifiers |
| MQG-03 | LCC | Populate Library of Congress Classification metadata |
| MQG-05 | Description / Comments | Build rich HTML comments using AI-assisted rules |
| MQG-06 | Tags | Build and clean tags using a controlled ruleset |

## Parked or Manual MQGs

Some MQGs should not be normal tool workflows right now.

| MQG | Status | Reason |
|---|---|---|
| MQG-04 Awards | Parked as standalone workflow | Award information may later live inside Comments or a future structured awards model |
| MQG-07 Cover | Manual only | Cover work does not need this PowerShell workflow tool |
| MQG-99 Metadata Complete | Manual final gate | The user expects to mark this manually in Calibre |

## MQG Principle

MQG fields are evidence markers, not casual task checkboxes.

A field should be marked complete only after appropriate evidence exists, such as:

- source export,
- proposal worksheet,
- validation,
- human review,
- preflight,
- controlled apply,
- Calibre readback verification,
- audit/report output.

## Target Selection Model

Every productive workflow should begin with:

Which books should be processed?

The toolkit should support:

1. Paste a Calibre search string.
2. Process all books missing the selected MQG.
3. Use an existing batch manifest.

This supports both large backlog processing and future maintenance work.

## Backlog Mode

Backlog mode is for the current state where large portions of the library still need metadata processing.

The tool should support:

- processing all records missing a selected MQG,
- showing the count before proceeding,
- limiting to the first N records,
- saving a batch without applying changes,
- chunking large work into manageable runs.

## Maintenance Mode

Maintenance mode is for the future state where most records are complete and the user is mostly catching strays, new additions, or new award-year batches.

The tool should support:

- pasted Calibre search strings,
- recent additions,
- all remaining incomplete records for a specific MQG,
- reusable batch manifests.

## Hidden Plumbing Philosophy

Reports, diagnostics, validation files, and preflight files are important, but they should not dominate the main user experience.

The tool may generate internal artifacts for:

- tool state,
- AI input,
- audit trail,
- review/approval,
- troubleshooting.

The normal launcher should show reports only when they support a user decision.

## Safety Model

Write-capable workflows should preserve these rules:

1. Generate source or proposal artifacts first.
2. Validate before apply.
3. Require explicit confirmation before writing to Calibre.
4. Treat Calibre as closed before write operations.
5. Recheck current Calibre metadata before writing when practical.
6. Skip unsafe rows instead of force-writing.
7. Write only the intended field or fields.
8. Read back from Calibre where practical.
9. Produce an audit artifact.
10. Stop on exceptions and inspect before continuing.

## AI Boundary

AI may propose metadata.

AI should not be the final authority that marks metadata complete.

The preferred model is:

1. AI proposes.
2. User reviews when needed.
3. Tool validates.
4. Tool applies only with explicit confirmation.
5. Tool verifies with Calibre readback.
6. MQG completion happens only after evidence exists.

## Current Validated Identifier Milestone

As of v0.11.0, the MQG-02 Identifier workflow has a validated completion path.

The workflow successfully marked 124 preflight-approved Identifier records complete with zero failures.

Post-apply state:

- Ready to mark complete: 0
- Already complete: 4,134
- Skipped/manual review: 958

Identifier I6 is now launcher-accessible as:

I6. Identifiers: Mark preflight-approved MQG-02 complete

## Naming Compatibility

The product name is:

Calibre Metadata Toolkit

Historical implementation names may remain for compatibility:

- repo: `calibre-lcc-toolkit`,
- folder: `lcc-toolkit`,
- launcher: `Start-LccWorkflow.ps1`,
- config: `lcc-toolkit.config.json`.

A staged compatibility-first rename is preferred over a big-bang rename.

## Current Roadmap Direction

Near-term design direction:

1. Productive launcher shell.
2. Shared target selection helper.
3. MQG-01 guided Title & Author workflow.
4. MQG-03 guided LCC workflow.
5. MQG-02 identifier proposal engine design.
6. MQG-05 Comments Builder workflow.
7. MQG-06 Tags ruleset and proposal workflow.

## What This Document Is Not

This is not the full user manual.

The full manual should wait until the launcher and target-selection model are closer to stable.

This orientation document exists to explain what the tool is becoming and how future development should stay aligned.
