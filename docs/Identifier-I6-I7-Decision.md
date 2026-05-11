# Identifier I6/I7 Decision - MQG-02 Completion Apply and Verification

## Decision

I6 will be a conservative MQG-02 completion apply step.

For the first implementation, I6 will only mark `#mqg_identifiers` as complete for rows already proven safe by the I5 MQG-02 completion preflight. I6 will not repair, normalize, add, delete, or rewrite identifier values.

I7 will remain a conceptual verification/readback step. The first I6 implementation may produce its own verification/readback report, but the workflow design should preserve a clear separation between:

1. apply intent,
2. write operation,
3. Calibre readback verification,
4. audit/report output.

A future release may expose I7 as a dedicated launcher option if that improves operator clarity.

## Why

MQG fields are verified evidence markers, not casual task checkboxes.

The Identifier workflow already has a staged safety model:

1. inventory,
2. diagnostics,
3. proposal worksheet,
4. proposal validation,
5. MQG-02 completion preflight,
6. apply only proven-safe completions,
7. verify with readback evidence.

The safest first write-capable Identifier step is to mark only the remaining preflight-approved records as MQG-02 complete.

## Alternatives Considered

### Alternative 1 - I6 repairs identifiers and marks MQG-02 complete

Rejected for now.

This combines identifier metadata mutation with MQG status completion. That increases risk and makes it harder to audit what changed.

Identifier repair, normalization, enrichment, or AI-assisted identifier cleanup should be handled in a later workflow.

### Alternative 2 - I6 marks all proposal-valid rows complete

Rejected.

The I5 preflight is the stronger evidence source because it checks current Calibre state before apply. The proposal worksheet may be stale by the time a write operation occurs.

### Alternative 3 - I6 blocks MQG-02 completion when MQG-01 is incomplete

Rejected for now.

MQG-02 is early in the workflow. The existing Calibre database already contains thousands of rows where `#mqg_identifiers` is complete even if MQG-01 may not be complete.

Title/author MQG state can be reported as context, but it should not block MQG-02 completion unless the rule is intentionally redesigned later.

### Alternative 4 - I7 is immediately added as a separate launcher option

Deferred.

The launcher is already becoming crowded. The first implementation should avoid worsening operator complexity unless a separate I7 option clearly improves safety or usability.

## Safety Implications

I6 must be write-gated and conservative.

Before writing, I6 must require an explicit confirmation phrase:

MARK MQG-02 COMPLETE

I6 must treat Calibre as needing to be closed before write operations.

I6 must only write rows where the I5 preflight artifact indicates:

- `PreflightStatus = Ready - Future MQG-02 Apply`
- `FutureApplyEligible = Yes`
- `PreflightIssueCount = 0`

I6 must also re-check current Calibre metadata before writing and verify:

- current `#mqg_identifiers` is still false/no,
- current title has not drifted from the preflight evidence,
- current author has not drifted from the preflight evidence,
- the Calibre record still exists,
- no unexpected pre-write blocker is present.

Rows that fail current-state checks must be skipped and reported, not force-written.

## User Workflow Impact

The user can run I5 to generate the official MQG-02 completion preflight artifact, review the ready rows, then run I6 to mark only verified-safe records complete.

This avoids requiring manual TSV edits for safe rows while preserving auditability.

The expected first-use case is a small set of rows, such as the currently known 124 records identified as:

Ready - Future MQG-02 Apply

## Official Audit Artifacts

The I5 preflight CSV remains the evidence input artifact.

I6 should produce an apply report showing:

- rows reviewed,
- rows eligible,
- rows written,
- rows skipped,
- rows blocked,
- rows already complete,
- write failures,
- verification failures.

I6 should also produce a readback/verification report showing the final observed Calibre value for `#mqg_identifiers`.

## Development Thread Action

Implement v0.10.8 as a narrow release.

Recommended implementation sequence:

1. Add this decision document.
2. Add `scripts/Invoke-IdentifierMqgComplete.ps1`.
3. Keep the script conservative and write-gated.
4. Parser-check the new script.
5. Run read-only / no-write validation first.
6. Only then test the explicit confirmation path.
7. Decide whether launcher wiring belongs in v0.10.8 or a follow-up release after script validation.

## Current Scope Boundary

For v0.10.8, do not implement:

- identifier repair,
- identifier normalization writes,
- identifier enrichment,
- AI-assisted identifier decisions,
- new Comments/Tags automation,
- launcher redesign,
- broad module expansion.

The release goal is only:

Safely mark verified MQG-02 Identifier rows complete, with audit evidence and readback verification.
