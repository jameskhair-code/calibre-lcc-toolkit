# MQG Workflow Architecture

## 1. Purpose

This document defines the canonical Metadata Quality Gate (MQG) processing order for the Calibre Metadata Toolkit.

The goal is to support a one-pass workflow where selected books move through each metadata gate in the smartest order, with each gate verified before its MQG checkbox is marked complete.

The long-term vision is:

    Select book or batch
    -> process each MQG in order
    -> pause for manual gates where required
    -> verify each gate
    -> mark each MQG checkbox complete only after verification
    -> mark MQG-99 Metadata Complete only after all required gates are complete

## 2. Canonical MQG Processing Order

The current canonical order is:

| Order | Display Label | Stable Lookup Name | Gate Type | Notes |
|---:|---|---|---|---|
| 1 | MQG-01: Title & Author | #mqg_title_author | Automated / verified | Core bibliographic identity. Must come first. |
| 2 | MQG-02: Identifiers | #mqg_identifiers | Future automated / semi-automated | ISBN, LCCN, and other identifiers improve downstream lookup confidence. |
| 3 | MQG-03: LCC | #mqg_lcc | Automated / verified | Classification backbone for later comments and tags. |
| 4 | MQG-04: Awards | #mqg_awards | Manual / toolkit-tracked | Awards should be finalized before final comments are generated. |
| 5 | MQG-05: Description / Comments | #mqg_description | Automated / reviewed / verified | Final curator-style comments should use known title, author, identifiers, LCC, and awards context. |
| 6 | MQG-06: Tags | #mqg_tags | Future automated / reviewed | Tags should be final, not starter tags, and should follow comments/context work. |
| 7 | MQG-07: Cover | #mqg_cover | Manual / toolkit-tracked | Cover work is presentation quality and can be completed after intellectual metadata. |
| 99 | MQG-99: Metadata Complete | #mqg_metadata_complete | Final automated gate | Should only be marked after required prior MQGs are complete. |

## 3. Stable Lookup Name Rule

Only the Calibre display labels were changed to reflect the new order.

The lookup names must remain stable:

    #mqg_title_author
    #mqg_identifiers
    #mqg_lcc
    #mqg_awards
    #mqg_description
    #mqg_tags
    #mqg_cover
    #mqg_metadata_complete

Scripts should target lookup names, not display labels.

Do not rename lookup names unless there is a deliberate migration plan.

## 4. Why This Order

### MQG-01: Title & Author

Title and author cleanup must happen first because every downstream lookup depends on the book being correctly identified.

### MQG-02: Identifiers

Identifiers improve confidence for classification, awards, comments, cover matching, and deduplication.

### MQG-03: LCC

LCC should come before final comments because it gives the comments generator a classification spine.

MQG-03 requires all four LCC fields to be populated and verified before the gate is complete:

    LCC
    LCC Classification Path
    LCC Primary Class
    LCC Secondary Class

### MQG-04: Awards

Awards should come before comments because award recognition is meaningful context for the final comments block.

### MQG-05: Description / Comments

Comments should be generated after title, author, identifiers, LCC, and awards are known.

### MQG-06: Tags

Tags should be final tags, not starter tags. They should be informed by the completed metadata context.

### MQG-07: Cover

Cover work is manual and presentation-focused. It does not need to inform the intellectual metadata flow.

### MQG-99: Metadata Complete

MQG-99 should eventually be an automated final gate.

The final gate should only pass when all required MQG fields are true and no blocking conditions remain.

## 5. Gate Completion Pattern

The preferred pattern for each MQG is:

    Export candidates
    -> prepare or perform enrichment
    -> dry run or review
    -> apply or manually complete work
    -> verify
    -> mark MQG complete

For automated gates, MQG checkboxes should not be marked during export, dry run, summary, or initial apply.

They should be marked only after verification confirms the expected final state.

## 6. Current Proven Pattern

The Author / Title workflow now proves the pattern:

    A1 Export
    A2 Dry Run
    A3 Summary
    A4 Apply
    A5 Verify
    A6 Mark verified MQG complete

A6 reads the verify report as the source of truth and only marks records with:

    VerificationStatus = Verified

It then writes:

    #mqg_title_author = true

and performs post-write readback confirmation.

## 7. Manual Gates

Some gates are intentionally manual.

Current manual or likely-manual gates:

    MQG-04: Awards
    MQG-07: Cover

The toolkit does not need to perform all manual work directly.

However, it should still provide a safe completion step:

    Manual work complete
    -> user confirms
    -> optional readback/check
    -> mark MQG field true
    -> report result

## 8. Future One-Pass Workflow Vision

The long-term goal is a guided one-pass workflow for individual books or selected batches.

A future full workflow could look like:

    Process selected book or batch
    -> run MQG-01 Title & Author
    -> run MQG-02 Identifiers
    -> run MQG-03 LCC
    -> pause for MQG-04 Awards review
    -> run MQG-05 Description / Comments
    -> run MQG-06 Tags
    -> pause for MQG-07 Cover review
    -> run MQG-99 final completion check

The toolkit should remain operator-safe, report-driven, and reversible through review before write operations.

## 9. Operating Rule

When in doubt:

    Verify first.
    Mark MQG complete second.
    Mark MQG-99 last.

