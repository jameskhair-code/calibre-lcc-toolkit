# MQG-01 Author/Title Workbench Design

## 1. Purpose

MQG-01 is the foundation workflow for the Calibre Metadata Toolkit.

Its job is to make book title and author metadata reliable enough that later workflows can perform better:

- MQG-02 Identifier cleanup
- MQG-03 LCC classification
- MQG-05 Comments generation
- MQG-06 Tags generation

The long-term operator goal is simple:

    Press 1.
    Choose the target books.
    Review what would change and why.
    Approve only when confident.

The internal toolkit may create manifests, exports, reports, review files, and audit artifacts, but normal Productive Launcher usage should not require the operator to manage those artifacts manually.

## 2. Design posture

MQG-01 should be treated as a sub-tool / workbench, not a one-time script wrapper.

The workflow should be iterated repeatedly until it becomes:

- easy to start,
- clear about what it found,
- clear about what it would change,
- clear about why it would change it,
- safe to review,
- safe to apply,
- practical for daily use.

Do not move on to MQG-02 as the primary implementation focus until MQG-01 feels genuinely useful and polished.

## 3. Operator-facing ideal workflow

The desired daily-use flow should eventually look like this:

    Select an option: 1

    MQG-01: Clean Title & Author

    Paste Calibre search string:
    > #mqg_title_author:false

    Found:
    - Books in scope: 4,812
    - Already MQG-01 complete: 0
    - Not MQG-01 complete: 4,812

    Analyze title/author metadata now? [YES]:

    Analyzing...

    Results:
    - No change recommended: 3,902
    - Change proposed: 612
    - Manual review: 298
    - Errors: 0

    What do you want to do?
    1. Show proposed changes
    2. Export AI/manual review packet
    3. Apply safe mechanical changes only
    4. Open detailed review artifact
    5. Stop

The operator should not need to understand or operate:

- batch manifests,
- source TSVs,
- proposal TSVs,
- dry-run reports,
- verify reports,
- internal batch IDs,
- internal output folders.

Those may still exist, but they should be hidden by default.

## 4. Current Productive Launcher foundation

As of v0.12.3, the Productive Launcher can:

- select MQG workflow,
- accept target selection,
- create or reuse a stable batch manifest,
- auto-generate manifest and summary report paths,
- report row count,
- stop before downstream processing.

This is useful scaffolding, but MQG-01 should now evolve beyond generic target selection into a real workbench.

The target-selection and batch-manifest layer remains valuable internally because it gives the workflow:

- repeatability,
- stable book scope,
- audit trail,
- row counts,
- future resume/retry support,
- safe boundaries for AI review.

The operator should experience this as:

    Preparing MQG-01 review set...

not:

    Creating batch manifest...

## 5. Visible vs hidden architecture

### 5.1 Visible to operator

The operator-facing MQG-01 workbench should show:

- target query or selected batch name,
- count of books found,
- count of books already complete,
- count of books needing MQG-01 review,
- count of proposed changes,
- count of no-change rows,
- count of manual-review rows,
- count of errors,
- preview of proposed changes,
- reason for each proposed change,
- next action menu.

### 5.2 Hidden by default

The following artifacts may be created internally, but should not be required in normal operation:

- batch manifest CSV,
- Author/Title source TSV,
- rule evaluation TSV,
- AI review packet,
- proposal TSV,
- dry-run CSV,
- summary TXT/MD/HTML,
- apply CSV,
- verify CSV.

These artifacts should be surfaced only when useful:

- review needed,
- approval needed,
- troubleshooting,
- audit,
- recovery,
- handoff to AI.

## 6. Proposed MQG-01 workflow pipeline

The eventual MQG-01 pipeline should be:

    Target
    -> Count
    -> Export current metadata
    -> Analyze with rules
    -> Generate proposals
    -> Preview impact
    -> Review / approve
    -> Dry run
    -> Apply
    -> Verify
    -> Mark MQG-01 complete

Implementation should be incremental.

### 6.1 Target

Use the Productive Launcher target-selection model:

- pasted Calibre search string,
- all books missing MQG-01,
- existing batch manifest.

The Productive Launcher should translate this into a stable internal work set.

### 6.2 Count

Before analysis, show:

- books found by query,
- books already MQG-01 complete,
- books not yet MQG-01 complete,
- books available for analysis.

This gives the operator confidence that the target scope is correct.

### 6.3 Analyze

Read current title/author fields and evaluate them with the MQG-01 rule system.

The analyze step should not modify Calibre metadata.

### 6.4 Generate proposals

For each row, produce a status:

- No Change
- Safe Mechanical Change
- Change Proposed
- Manual Review
- Already Complete
- Error

Every row with a proposed change must include:

- current title,
- proposed title,
- current authors,
- proposed authors,
- rule ID or rule group,
- reason,
- confidence,
- review action.

### 6.5 Preview

Show summary counts and a readable preview before any apply step.

Suggested preview:

    MQG-01 Analysis Results

    Books analyzed: 200
    Already complete: 12
    No change: 143
    Safe mechanical changes: 18
    Review-required changes: 19
    Manual review: 8
    Errors: 0

Then show a small sample of proposed changes.

### 6.6 Review / approve

The workflow should support at least three review modes:

1. safe mechanical changes only,
2. AI/manual review packet,
3. explicit approved proposal file.

No ambiguous or review-required change should be applied without approval.

### 6.7 Apply

Apply should be opt-in, write-capable, and guarded.

Before writing:

- show number of rows to change,
- show whether titles, authors, or both will change,
- require explicit confirmation phrase.

### 6.8 Verify

After apply:

- read current Calibre state,
- confirm applied values,
- write verify report,
- summarize failures or mismatches.

### 6.9 Mark MQG complete

MQG-01 should only be marked complete when:

- there is no proposed change,
- safe change was applied and verified,
- approved change was applied and verified,
- manual review determined no change is needed.

Manual review rows should not be silently marked complete.

## 7. Rule system

MQG-01 should use a living rule system.

Existing rule assets should be reused and improved where practical:

- `docs/Author-Title-Normalization-Rules.md`
- `config/author-title-normalization-rules.json`

The rule system should be readable by humans and stable enough for AI-assisted review.

### 7.1 Rule categories

#### Safe mechanical rules

These may eventually be eligible for safe-only apply.

Examples:

- trim leading/trailing whitespace,
- collapse repeated internal spaces,
- remove accidental double punctuation,
- normalize spacing around colons,
- remove obvious trailing import artifacts,
- normalize simple all-caps titles only when confidence is high.

#### Suggested change rules

These should propose a change but require review.

Examples:

- subtitle boundary cleanup,
- bracketed metadata removal,
- series text removal from title,
- author role cleanup,
- `Lastname, Firstname` author normalization,
- title casing beyond simple mechanical cases.

#### Manual review rules

These should flag rows without proposing a direct write.

Examples:

- author contains editor/translator/illustrator role text,
- title appears truncated,
- title contains multiple works,
- title/author seems mismatched against identifiers,
- organization vs person authorship is ambiguous,
- multiple plausible canonical forms exist.

#### Never-auto rules

These should prevent automatic apply.

Examples:

- uncertain author identity,
- non-English title casing ambiguity,
- ancient/classical works with variant title conventions,
- religious texts or anthologies with complex attribution,
- multi-author or edited-volume ambiguity.

## 8. Proposal statuses

Use a clear proposal status model.

| Status | Meaning | Apply Eligibility |
|---|---|---|
| Already Complete | MQG-01 already checked | No action |
| No Change | Rule engine found no needed change | Can later mark complete |
| Safe Mechanical Change | Low-risk cleanup proposed | Safe-only apply candidate |
| Change Proposed | Useful but needs review | Review required |
| Manual Review | Cannot determine safe proposal | No auto-apply |
| Error | Analysis failed | No auto-apply |

## 9. Proposed output columns

The MQG-01 analysis/proposal output should include enough context to review safely.

| Column | Purpose |
|---|---|
| CalibreId | Stable Calibre record ID |
| TitleCurrent | Current Calibre title |
| AuthorsCurrent | Current Calibre authors |
| TitleProposed | Proposed title |
| AuthorsProposed | Proposed authors |
| TitleWouldChange | Yes/No |
| AuthorsWouldChange | Yes/No |
| ProposalStatus | No Change / Change Proposed / Manual Review / etc. |
| Confidence | High / Medium / Low |
| RuleIds | Rule IDs that fired |
| Reason | Human-readable reason |
| ReviewAction | Suggested next action |
| MQGTitleAuthor | Current MQG-01 field state |
| Identifiers | Useful external IDs for review |
| ISBN | ISBN if present |
| Series | If available later |
| Notes | Additional review notes |

## 10. Review experience

The operator should be able to see:

- what would change,
- why it would change,
- whether the change is safe,
- whether manual review is needed.

A readable review table should prioritize:

1. rows with safe mechanical changes,
2. rows with review-required proposed changes,
3. manual review rows,
4. errors,
5. no-change rows.

The review should not drown the operator in rows that do not need action.

## 11. AI-assisted review model

AI should eventually assist MQG-01 by reviewing the proposal packet, not by blindly changing Calibre.

The recommended AI flow:

    Toolkit exports MQG-01 review packet
    AI reviews title/author issues using the approved rules
    AI returns proposed changes with reasons
    Toolkit dry-runs proposed changes
    Operator reviews summary
    Operator applies only approved changes
    Toolkit verifies

The AI packet should include:

- current metadata,
- identifiers,
- rule profile/version,
- examples,
- required output schema,
- constraints,
- warning not to invent facts when uncertain.

## 12. Apply safety model

MQG-01 apply should follow these principles:

- never write without explicit confirmation,
- never apply Manual Review rows,
- never apply Error rows,
- safe-only apply should include only safe mechanical changes,
- review-required changes need an approved proposal file,
- apply report must record readback verification,
- verify report should be available after apply.

## 13. Productive Launcher UX principles

For MQG-01, the Productive Launcher should:

- use friendly language,
- ask fewer questions,
- auto-generate artifact paths,
- only ask follow-up questions when a real decision is required,
- hide manifests and exports unless useful,
- show counts before deeper action,
- show proposed changes before apply,
- preserve advanced scripts for troubleshooting.

Avoid exposing internal terms like:

- slug,
- canonicalize,
- dry-run artifact,
- internal report path,

unless the operator opens Advanced Tools or troubleshooting mode.

## 14. Near-term implementation sequence

### v0.12.5 - MQG-01 Analyze/Preview Shell

Goal:

    Press 1
    -> choose target
    -> create/reuse internal manifest
    -> export/read source metadata
    -> show basic counts
    -> stop

No proposal engine yet.

### v0.12.6 - MQG-01 Rule Evaluation Report

Goal:

    Run current title/author rows through initial rules
    -> produce ProposalStatus
    -> produce Reason
    -> produce counts
    -> generate review CSV/HTML

No apply.

### v0.12.7 - MQG-01 AI Review Packet

Goal:

    Create AI-ready packet for proposed title/author cleanup
    -> include rules profile
    -> include target rows
    -> include required output schema
    -> stop

No apply.

### v0.12.8 - MQG-01 Proposal Import and Dry Run

Goal:

    Accept approved proposal TSV
    -> validate schema
    -> dry run changes
    -> summarize impact

No apply by default.

### v0.12.9 - MQG-01 Safe Apply and Verify

Goal:

    Apply explicitly approved/safe changes
    -> verify readback
    -> summarize result

Write-capable and confirmation-gated.

## 15. Definition of daily-usable MQG-01

MQG-01 should be considered daily-usable when the operator can:

- press Productive option 1,
- provide a target query,
- see how many books are in scope,
- see how many are already complete,
- see how many need action,
- see proposed changes with reasons,
- export a useful AI/manual review packet,
- apply only reviewed/safe changes,
- verify results,
- avoid manual artifact juggling in normal usage.

The target state is:

    I can run MQG-01 on real batches without dreading it.

## 16. Open design questions

Questions to resolve during MQG-01 iteration:

1. What exact initial rules belong in the safe mechanical category?
2. Should title casing ever be safe-auto, or always review-required?
3. How should author role text be represented when preserved?
4. Should sort title be included later?
5. Should series metadata be included as review context?
6. What is the ideal review file format: CSV, TSV, HTML, Markdown, or multiple?
7. How many preview rows should be shown in console?
8. Should no-change rows be hidden by default in review artifacts?
9. How should MQG-01 completion marking handle manual review rows?
10. How should AI review packets be chunked for large batches?

## 17. Current decision

Decision for v0.12.4:

- Focus the roadmap on MQG-01 Author/Title until it becomes genuinely useful and polished.
- Do not move primary implementation focus to MQG-02 yet.
- Treat MQG-01 as a workbench.
- Keep internal artifacts available but hidden from normal Productive Launcher operation.
- Use rules, proposal statuses, reasons, and review summaries as the trust backbone.
