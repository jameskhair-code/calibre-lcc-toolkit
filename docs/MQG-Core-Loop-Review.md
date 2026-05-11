# MQG Core Loop Review - v0.11.0

## Purpose

This document captures the current state of the Calibre Metadata Toolkit core workflow after the Identifier MQG-02 apply path was successfully validated.

The goal of v0.11.0 is not to add feature sprawl. The goal is to review the core MQG loop, decide what belongs in the launcher, and stabilize the operator experience before expanding heavier Comments, Tags, Awards, Covers, or AI-assisted workflows.

## Current Project Identity

The project is historically named `calibre-lcc-toolkit`, but it is now functioning as a broader Calibre Metadata Toolkit.

The toolkit uses:

- `calibredb.exe`
- PowerShell workflow scripts
- `Start-LccWorkflow.ps1` as the launcher
- TSV and CSV audit artifacts
- Calibre custom fields as MQG evidence markers
- explicit proposal, validation, apply, and verify phases

The project goal is to make Calibre metadata cleanup:

- repeatable
- safe
- reviewable
- auditable
- usable months from now
- guided where practical
- conservative with write operations

## Core Workflow Target

The practical user workflow is:

1. Select a batch of books.
2. Clean title and author metadata.
3. Confirm identifiers.
4. Populate LCC classification.
5. Handle awards, comments, tags, and cover review as needed.
6. Verify MQG status.
7. Mark metadata complete only when evidence exists.

## MQG Gates

Current MQG gates:

- MQG-01 Title and Author
- MQG-02 Identifiers
- MQG-03 LCC
- MQG-04 Awards
- MQG-05 Description / Comments
- MQG-06 Tags
- MQG-07 Cover
- MQG-99 Final / Metadata Complete

Important custom fields:

- `#mqg_title_author`
- `#mqg_identifiers`
- `#mqg_lcc`
- `#mqg_awards`
- `#mqg_description`
- `#mqg_tags`
- `#mqg_cover`
- `#mqg_metadata_complete`

## Architectural Principle

MQG fields are not casual task checkboxes.

They are evidence markers. A field should be marked complete only after the relevant workflow has produced sufficient evidence through one or more of:

- source export
- proposal worksheet
- validation
- human review
- preflight
- controlled apply
- Calibre readback verification
- audit report output

## Current Core Status

### MQG-01 Title and Author

Current state:

- Author/Title cleanup module exists.
- Export, dry run, summary, apply, verify, and MQG completion paths exist.
- Launcher exposes A1 through A6.
- Existing safety pattern includes review artifacts, apply confirmation, and verification.

Current assessment:

- MQG-01 has a working workflow and launcher exposure.
- This appears to be the strongest model for future module safety patterns.

Open questions:

- Should MQG-01 status become a recommended prerequisite for later gates?
- Should it remain contextual only for MQG-02?
- Should batch status reporting better explain when MQG-01 is incomplete but later MQG gates are complete?

### MQG-02 Identifiers

Current state:

- Identifier inventory, diagnostics, proposal worksheet, proposal validation, and completion preflight exist.
- Launcher exposes I1 through I5.
- A conservative apply script now exists:
  - `scripts/Invoke-IdentifierMqgComplete.ps1`
- I6 is not currently wired into the launcher.
- The apply script does not repair, normalize, add, delete, or rewrite identifier values.
- It only marks `#mqg_identifiers:true` for rows proven safe by I5 and rechecked against current Calibre metadata.

Validated result:

- The apply path reviewed 5,092 rows.
- 124 rows were newly marked MQG-02 complete.
- 4,010 rows were already complete before apply.
- 0 rows failed.
- 958 rows remained skipped/manual review.
- Post-apply read-only check confirmed:
  - Ready to mark complete: 0
  - Already complete: 4,134
  - Skipped/manual review: 958

Current assessment:

- MQG-02 now has a validated end-to-end completion path.
- The write-capable path works manually.
- The question is no longer whether I6 works.
- The question is how to expose it safely without worsening launcher complexity.

Open questions:

- Should I6 be wired into the current Identifier Module menu?
- Should I7 exist as a separate verification/readback report?
- Should I6 stay advanced/manual until the launcher is reorganized?
- Should post-apply verification be considered sufficient inside I6, or should a separate I7 remain architecturally preferred?
- How should the remaining 958 manual-review Identifier rows be handled in future releases?

### MQG-03 LCC

Current state:

- LCC workflow exists and is historically the foundation of the toolkit.
- Launcher exposes export, prepare, validate, apply, verify, and MQG completion paths.
- LCC MQG completion already has a write-safety model.

Current assessment:

- MQG-03 has a mature operational workflow.
- It should be reviewed alongside MQG-01 and MQG-02 as part of the stable core loop.

Open questions:

- Should LCC workflow be conceptually renamed or grouped under the broader Calibre Metadata Toolkit identity?
- Should LCC remain the default visible workflow at the top of the launcher?
- Should LCC-specific options move under a module grouping in a future launcher redesign?

## Launcher State

The current launcher is functional but increasingly crowded.

Current visible structure includes:

- numbered general LCC workflow options
- Batch Selection Module
- Guided Workflows
- Author / Title Cleanup Module
- Comments Module
- Identifier Module
- Manual MQG Completion Module

Current assessment:

- The launcher exposes useful tools but is becoming script-list oriented.
- Adding I6 directly is easy, but may worsen menu sprawl.
- A more workflow-oriented launcher is likely needed soon.

Potential future launcher organization:

1. Guided Batch Workflows
2. Core MQG Workflow
3. Module Workflows
4. MQG Status and Completion
5. Reports and Review Artifacts
6. Configuration and Rules
7. Developer / Advanced Tools

## Decision Candidates

### Decision Candidate 1 - Wire I6 Now

Decision:

Wire I6 into the current Identifier Module menu as:

- `I6. Identifiers: Mark verified MQG complete`

Why this may be appropriate:

- The script has been validated.
- It follows explicit confirmation and readback patterns.
- It completes the currently visible I1-I5 Identifier sequence.

Risk:

- Adds another launcher option to an already crowded interface.
- May encourage users to run I6 without understanding I5 evidence.

Mitigation:

- Launcher text can explicitly say "verified" or "preflight-approved."
- Script itself remains safe-gated.

### Decision Candidate 2 - Add I7 Verify Option

Decision:

Add a dedicated I7 verification/readback option.

Why this may be appropriate:

- Preserves apply and verify separation.
- Matches the mental model of other modules.
- Gives the operator a post-apply check without rerunning I6 in preflight mode manually.

Risk:

- Adds even more launcher surface area.
- May be redundant because I6 already verifies readback.

Mitigation:

- I7 could be deferred until launcher reorganization.
- I6 output/report may be enough for now.

### Decision Candidate 3 - Pause Launcher Wiring

Decision:

Do not wire I6 yet. Keep it as a manual advanced script until the launcher is reorganized.

Why this may be appropriate:

- Avoids adding more menu sprawl.
- Aligns with the project architect guidance to pause feature expansion.
- Encourages a cleaner workflow redesign before exposing more tools.

Risk:

- The Identifier module appears incomplete in the launcher.
- The operator must remember the manual script command.

Mitigation:

- Add documentation pointing to the manual I6 command.
- Revisit I6 launcher wiring after core-loop review.

## Recommended v0.11.0 Direction

Recommended v0.11.0 scope:

1. Capture this MQG core-loop review.
2. Confirm whether I6 should be launcher-wired now or deferred.
3. Avoid Comments/Tags expansion in this release.
4. Avoid AI-assisted metadata expansion in this release.
5. If wiring I6, do it as a narrow release increment with no unrelated changes.
6. If not wiring I6, document the manual command and move to launcher redesign planning.

## Current Recommendation

The current recommendation is to wire I6 only if the launcher text can make the safety path obvious.

Suggested label:

- `I6. Identifiers: Mark preflight-approved MQG-02 complete`

This is more explicit than:

- `I6. Identifiers: Mark verified MQG complete`

Reason:

The phrase "preflight-approved" directly reminds the operator that I6 depends on I5 evidence.

Recommended next step:

Create a small decision after reviewing this document:

- wire I6 in v0.11.0,
- add I7 verification,
- or defer both until launcher redesign.

## Out of Scope for v0.11.0

Do not implement in this release:

- identifier repair
- identifier normalization writes
- AI-assisted identifier enrichment
- Comments generation expansion
- Tags automation expansion
- Awards automation expansion
- Cover automation expansion
- full launcher redesign unless intentionally selected as the release goal
- MQG-99 final completion automation

## Operational Safety Rules To Preserve

For write-capable workflows:

1. Generate source/report artifact first.
2. Validate before apply.
3. Require explicit confirmation.
4. Treat Calibre as closed before writes.
5. Recheck current Calibre metadata before writing when practical.
6. Skip unsafe rows rather than force-writing.
7. Write only the intended field.
8. Read back from Calibre.
9. Produce an audit report.
10. Stop on exceptions and inspect output before continuing.

## Review Status

Status: Draft for v0.11.0 development discussion.

Next action:

Review this document, then decide whether v0.11.0 should:

1. wire Identifier I6 into the launcher,
2. add a separate I7 verification option,
3. document manual I6 usage and defer launcher changes,
4. or pivot into launcher simplification planning.
