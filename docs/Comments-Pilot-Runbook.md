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

Only the first row was populated with proposed comments.

The remaining two rows were intentionally left blank to confirm that incomplete rows block correctly.

## 4. Proposed Comment Strategy

The first pilot comment used:

```text
CommentsTemplateProfile = Scholarly Nonfiction
CommentsMode = Prepend
Confidence = Medium - Source Supported
ManualReviewRequired = No
```

`Prepend` was selected because the existing Calibre comments were substantial publisher-style descriptions. Prepend allows future structured curator comments to appear first while preserving existing comments underneath, once apply behavior exists.

## 5. Pilot Result

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

## 6. Observations

The pilot confirmed that:

- Existing comments hash comparison works.
- High-risk existing comments are detected.
- `Prepend` can be used safely for high-risk existing comments because it avoids replacement.
- Blank proposed rows are blocked.
- Missing template profile, comments mode, confidence, manual review value, proposed comments, and source notes are reported clearly.
- SourceNotes are required both as a workflow field and as a visible Source Notes HTML section.
- The summary gives enough information to review eligible and blocked rows.
- Calibre must be closed before `calibredb` can read the library directly.

## 7. Recommended Next Pilot

Next pilot should populate all three rows with real proposed comments using `Prepend`.

Recommended next test:

```text
5153 - Empire and Underworld
5175 - The Burdens of Brotherhood
5176 - You Are All Free
```

Expected next dry-run target:

```text
Rows reviewed: 3
Rows eligible for apply: 3
Rows blocked: 0
```

If that succeeds, the module is ready for a broader comments-generation dry-run batch.