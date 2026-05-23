# Comments Pilot Runbook

## 1. Purpose

This runbook captures the first real-world pilot for the v0.6 Comments module.

The goal of the pilot is to test whether the comments workflow can safely move from exported Calibre metadata to proposed structured comments, then through dry run and summary reporting, without writing anything to Calibre.

For v0.6, the Comments module remains limited to:

    Export -> Dry Run -> Summary

Apply and verify behavior are intentionally deferred.

## 2. Pilot Batch

Initial pilot batch:

    AHA - J. Russell Major Prize

Pilot records:

    5153 - Empire and Underworld - Miranda Frances Spieler
    5175 - The Burdens of Brotherhood: Jews and Muslims From North Africa to France - Ethan B. Katz
    5176 - You Are All Free: The Haitian Revolution and the Abolition of Slavery - Jeremy D. Popkin

## 3. Pilot Input

Source TSV:

    input/comments-source-j-russell-major-prize.tsv

Pilot import TSV:

    input/comments-import-pilot-j-russell-major-prize-3books.tsv

The pilot used exported Calibre metadata, existing comments, comment hashes, award-program context, identifiers, LCC classification context, and proposed structured HTML comments.

No Calibre metadata was modified during the pilot.

## 4. Proposed Comment Strategy

The pilot used:

    CommentsTemplateProfile = Scholarly Nonfiction
    CommentsMode = Prepend
    Confidence = Medium - Source Supported
    ManualReviewRequired = No

`Prepend` was selected because the existing Calibre comments were substantial publisher-style descriptions. Prepend allows future structured curator comments to appear first while preserving existing comments underneath, once apply behavior exists.

The pilot comments included:

- Overview
- Central Argument
- Why It Matters
- Why Read It
- Notable Details
- Themes & Threads
- Reading Experience
- Awards & Recognition
- Source Notes

SourceNotes were included both as a workflow field and as a visible HTML section.

## 5. First Pilot Result

The first pilot populated only the first row:

    5153 - Empire and Underworld

The remaining two rows were intentionally left blank to confirm that incomplete rows block correctly.

Dry-run result:

    Rows reviewed: 3
    Rows eligible for apply: 1
    Rows blocked: 2
    Rows missing proposed comments: 2
    Rows with high-risk existing comments: 3
    Rows with comments hash mismatch: 0
    Rows with blocked HTML: 0
    Rows missing source notes: 2
    Rows marked manual review: 0

Summary result:

    Rows reviewed: 3
    Rows eligible for apply: 1
    Rows blocked: 2

The populated `Empire and Underworld` row was accepted as apply-eligible by the dry-run safety gate.

The two blank rows were blocked as expected.

## 6. Second Pilot Result

The second pilot populated all three rows with real proposed comments using `Prepend`.

Pilot records:

    5153 - Empire and Underworld
    5175 - The Burdens of Brotherhood
    5176 - You Are All Free

Dry-run result:

    Rows reviewed: 3
    Rows eligible for apply: 3
    Rows blocked: 0
    Rows missing proposed comments: 0
    Rows with high-risk existing comments: 3
    Rows with comments hash mismatch: 0
    Rows with blocked HTML: 0
    Rows missing source notes: 0
    Rows marked manual review: 0

Summary result:

    Rows reviewed: 3
    Rows eligible for apply: 3
    Rows blocked: 0

This confirmed that `Prepend` is a viable mode for records with substantial existing comments, because the proposed structured comments can be reviewed without requiring replacement of existing publisher-style comments.

## 7. Observations

The pilot confirmed that:

- Existing comments hash comparison works.
- High-risk existing comments are detected.
- `Prepend` can be used safely for high-risk existing comments because it avoids replacement.
- Blank proposed rows are blocked.
- Fully populated proposed rows can pass the dry-run safety gate.
- Missing template profile, comments mode, confidence, manual review value, proposed comments, and source notes are reported clearly.
- SourceNotes are required both as a workflow field and as a visible Source Notes HTML section.
- The summary gives enough information to review eligible and blocked rows.
- Calibre must be closed before `calibredb` can read the library directly.
- The 3-book pilot supports the current v0.6 decision to stop at `Export -> Dry Run -> Summary`.

## 8. Pilot Conclusion

The v0.6 Comments module successfully supports:

- exporting comments source data
- preparing proposed structured comments externally
- validating proposed comments with a dry run
- detecting high-risk existing comments
- allowing safe `Prepend` rows when all required fields are present
- producing a readable summary
- protecting against incomplete proposed comments batches

The pilot supports the current v0.6 design decision to stop at:

    Export -> Dry Run -> Summary

Apply and verify behavior should remain deferred until a later milestone after more dry-run batches are reviewed.

## 9. Qualitative Acceptance Criteria

A comments pilot should not be considered successful merely because the dry run passes.

The proposed comments should also be reviewed for reading appeal and collection value.

For each proposed comment, ask:

    Does this make the book more discoverable?
    Does this make me more likely to open the book?
    Does the Why Read It section make a specific case for this book?
    Do the Notable Details include concrete hooks, either book-specific or subject-specific?
    Does Why It Matters explain significance beyond the award label?
    Does Awards & Recognition reflect researched recognition rather than only existing Calibre metadata?
    Are Source Notes clear enough to understand where the claims came from?

The target is not a generic summary.

The target is a source-grounded curator note that makes the book feel worth returning to.

## 10. Recommended Next Step

Run one broader dry-run-only batch with real proposed comments, likely 5-10 books, before designing any comments apply behavior.

Recommended next batch pattern:

    5-10 records
    CommentsMode = Prepend
    CommentsTemplateProfile = Scholarly Nonfiction
    Confidence = Medium - Source Supported or High - Source Grounded
    ManualReviewRequired = No
    SourceNotes populated
    Visible Source Notes HTML section present

If that succeeds, the project can decide whether the next milestone should be:

    v0.6.1 - Comments Pilot Refinement

or:

    v0.7 - Comments Apply and Verify

## 11. Five-Book Pilot Result

A broader 5-book pilot was run against the AHA - J. Russell Major Prize batch using real proposed comments for all five records.

Pilot records:

    5153 - Empire and Underworld
    5175 - The Burdens of Brotherhood
    5176 - You Are All Free
    5177 - Contraband
    5178 - Lethal Provocation

All five rows used:

    CommentsTemplateProfile = Scholarly Nonfiction
    CommentsMode = Prepend
    Confidence = Medium - Source Supported
    ManualReviewRequired = No

Dry-run result:

    Rows reviewed: 5
    Rows eligible for apply: 5
    Rows blocked: 0
    Rows missing proposed comments: 0
    Rows with high-risk existing comments: 5
    Rows with comments hash mismatch: 0
    Rows with blocked HTML: 0
    Rows missing source notes: 0
    Rows marked manual review: 0

Summary result:

    Rows reviewed: 5
    Rows eligible for apply: 5
    Rows blocked: 0

The summary confirmed:

- all five rows used the expected template profile
- all five rows used `Prepend`
- all five rows had expected confidence values
- all five rows passed HTML validation
- all five rows had SourceNotes populated
- all five rows had visible Source Notes HTML sections
- no placeholder text was detected
- no rows were blocked

This pilot confirmed that the comments workflow can scale beyond the initial 3-book pilot while still protecting substantial existing comments.

The proposed comment lengths ranged from roughly 2,700 to 3,300 characters, which appears to be a useful range for rich but manageable Calibre comments.

The pilot also reinforced that factual claims from external award or recognition research should be reviewed before any future apply workflow is introduced.

## 12. Operating Reminder

The Comments module is powerful because it can make the library more browsable and inviting.

It is also high-risk because the Calibre comments field may already contain substantial existing HTML or curated metadata.

For now:

    Do not apply comments.
    Do not overwrite comments.
    Dry run first.
    Summarize before review.
    Use Prepend for substantial existing comments.
    Keep Source Notes visible and auditable.