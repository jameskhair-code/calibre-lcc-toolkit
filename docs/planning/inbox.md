# Inbox — untriaged observations

Standing capture buffer for ideas noticed during real use. Not tied to any
single version. Entries are triaged and routed to a specific cycle (or the
ROADMAP parking lot) at each post-release re-audit, then cleared. Add freely;
routing is decided at version boundaries. See `docs/planning/workflow.md`
(phases 4–5) for the full lifecycle.

---

**TUI: highlight the selected pipeline step in the left panel.** The active
step shows in the right detail panel but the left ListView rows have no clear
selected-state treatment — hard to confirm focus at a glance when navigating
with arrows or digit-jumps. Display-only CSS change in `tui/app.py`
(`StepItem` highlighted/focused styling). Low risk. Pairs with v1.8 item 8
(both touch the TUI render path). Surfaced from real use 2026-05-28.

**AI author changes (especially removals) should be review-gated, not
auto-applied.** In a 500-book `clean-titles` run the AI removed an author
from "J R" (Joy Williams → William Gaddis only) based on its own training
knowledge, marked medium confidence, and it auto-applied under "apply all."
Correct in that instance, but authorship deletions from model memory are a
high-risk category that can silently corrupt data when wrong. Contrast: a
sibling entry in the same run correctly *flagged* a suspicious authorship
pairing ("The Tree of Life") for verification rather than changing it — that
is the desired behaviour. Make author-field changes consistent: flag /
review-gate rather than auto-apply at medium+, arguably cap authorship
removals at low/review-only. Touch points: confidence-tier assignment for
author-field changes in the clean-titles AI path (`rules/` for authors +
`modules/authors.py` tier handling). Smells like v1.8 (correctness theme).
Surfaced from real use 2026-05-28.

**`clean-titles` 429 rate-limit on large runs.** A 500-book run (50 batches,
5 in flight) hit the org's 8,000-output-tokens-per-minute cap; 1 of 50
batches failed with HTTP 429. Handled gracefully (failed-batch books not
marked complete; re-run retries them) but a clean large run shouldn't drop a
batch. Consider a 429-aware backoff that paces rather than just retries, or
throttling concurrency / batch-size when output-tokens-per-minute is the
binding limit. Likely affects all AI-suggest steps, not just clean-titles.
Touch points: `ai.py` `_run_batches_concurrent` / the retry path. Smells like
v1.10 (cost/perf) unless it recurs often. Surfaced from real use 2026-05-28.

**Consolidate the two parking lots.** Two parking lots currently coexist:
`ROADMAP.md`'s "Beyond v1.5" section and the parking lot in
`docs/planning/v2.0-plan-roadmap-construction.md`. `ROADMAP.md` is now mostly
historical — items 1–22, nearly all shipped through v1.5 — and the v2.0 plan
has largely superseded it as the forward-looking roadmap. Converge to one
forward parking lot (likely the v2.0 plan's) and demote `ROADMAP.md` to a
historical "what shipped through v1.5" record. Docs-only; small standalone
PR; doesn't block any cycle. Surfaced 2026-05-28 (process simplification).

**AI-judgment subject coherence (the replacement for the deferred keyword
approach).** v1.8 item 1 (keyword-based subject coherence) was prototyped and
deferred — ~70% false positives on a real 4,428-book batch, with the FPs
intrinsic to keyword-matching prose (metaphor: "a chess game of a novel";
incidental mention; comparison: "rivaled only by the Holocaust"; blurb
boilerplate), confirming the v1.4 reasoning. Candidate replacement: ask the AI
itself whether a book's *central* subject is substantive enough to warrant a
tag it lacks, rather than keyword-matching the prose. Likely better as an
opt-in *sweep tool* (scan the library for under-tagged books on high-value
subjects) than inline per-book warnings. Tonight's data seeds it:
Slavery / Holocaust / Colonialism are the high-value targets (~25–35% FP even
with keywords); the rest are noise. Needs its own cost + FP measurement before
adoption. Candidate for v1.9+/v2.0. Surfaced from v1.8 item 1 Phase A,
2026-05-28.

**Post-v2.0: major architect pass — full A-Z library-completeness model + UX
overhaul.** James's vision for after v2.0: rework the tool toward "every book
fully complete, every tracked dimension green." Includes a full
library-landscape view; tracking *every* aspect of a book A-to-Z including
currently-manual dimensions (e.g. covers — track completion status even if
editing stays manual, via a flag column that shows green in the menu); faster
menu navigation / button flow; an end-to-end workflow that "makes perfect
sense." Builds on existing primitives (the `#mqg_*` completion + manual flag
columns, `count_books_with_all_columns_true`, the TUI pipeline line) — an
extension of the completeness model plus a UX rebuild, not a from-scratch
rewrite. This is a v2.0-plan-scale architect pass (multi-version), to be scoped
at the post-v2.0 boundary in a web-Claude session. Surfaced 2026-05-28.
