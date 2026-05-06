# Comments Pilot Runbook

## 1. Purpose

This runbook captures the first real-world pilot for the v0.6 Comments module.

The goal of the pilot is to test whether the comments workflow can safely move from exported Calibre metadata to proposed structured comments, then through dry run and summary reporting, without writing anything to Calibre.

For v0.6, the Comments module remains limited to:

```text
Export -> Dry Run -> Summary
```

Apply and verify behavior are intentionally deferred.

## 2. Pilot Batch

Initial pilot batch:

```text
AHA - J. Russell Major Prize
```

Pilot records:

```text
5153 - Empire and Underworld - Miranda Frances Spieler
5175 - The Burdens of Brotherhood: Jews and Muslims From North Africa to France - Ethan B. Katz
5176 - You Are All Free: The Haitian Revolution and the Abolition of Slavery - Jeremy D. Popkin
```

## 3. Pilot Input

Source TSV:

```text
input/comments-source-j-russell-major-prize.tsv
```

Pilot import TSV:

```text
input/comments-import-pilot-j-russell-major-prize-3books.tsv
```

The pilot used exported Calibre metadata, existing comments, comment hashes, award-program context, identifiers, LCC classification context, and proposed structured HTML comments.

No Calibre metadata was modified during the pilot.

## 4. Proposed Comment Strategy

The pilot used:

```text
CommentsTemplateProfile = Scholarly Nonfiction
CommentsMode = Prepend
Confidence = Medium - Source Supported
ManualReviewRequired = No
```

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

```text
5153 - Empire and Underworld
```

The remaining two rows were intentionally left blank to confirm that incomplete rows block correctly.

Dry-run result:

```text
Rows reviewed: 3
Rows eligible for apply: 1
Rows blocked: 2
Rows missing proposed comments: 2
Rows with high-risk existing comments: 3
Rows with comments hash mismatch: 0
Rows with blocked HTML: 0
Rows missing source notes: 2
Rows marked manual review: 0
```

Summary result:

```text
Rows reviewed: 3
Rows eligible for apply: 1
Rows blocked: 2
```

The populated `Empire and Underworld` row was accepted as apply-eligible by the dry-run safety gate.

The two blank rows were blocked as expected.

## 6. Second Pilot Result

The second pilot populated all three rows with real proposed comments using `Prepend`.

Pilot records:

```text
5153 - Empire and Underworld
5175 - The Burdens of Brotherhood
5176 - You Are All Free
```

Dry-run result:

```text
Rows reviewed: 3
Rows eligible for apply: 3
Rows blocked: 0
Rows missing proposed comments: 0
Rows with high-risk existing comments: 3
Rows with comments hash mismatch: 0
Rows with blocked HTML: 0
Rows missing source notes: 0
Rows marked manual review: 0
```

Summary result:

```text
Rows reviewed: 3
Rows eligible for apply: 3
Rows blocked: 0
```

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

```text
Export -> Dry Run -> Summary
```

Apply and verify behavior should remain deferred until a later milestone after more dry-run batches are reviewed.

## 9. Recommended Next Step

Run one broader dry-run-only batch with real proposed comments, likely 5-10 books, before designing any comments apply behavior.

Recommended next batch pattern:

```text
5-10 records
CommentsMode = Prepend
CommentsTemplateProfile = Scholarly Nonfiction
Confidence = Medium - Source Supported or High - Source Grounded
ManualReviewRequired = No
SourceNotes populated
Visible Source Notes HTML section present
```

If that succeeds, the project can decide whether the next milestone should be:

```text
v0.6.1 - Comments Pilot Refinement
```

or:

```text
v0.7 - Comments Apply and Verify
```

## 10. Operating Reminder

The Comments module is powerful because it can make the library more browsable and inviting.

It is also high-risk because the Calibre comments field may already contain substantial existing HTML or curated metadata.

For now:

```text
Do not apply comments.
Do not overwrite comments.
Dry run first.
Summarize before review.
Use Prepend for substantial existing comments.
Keep Source Notes visible and auditable.
```