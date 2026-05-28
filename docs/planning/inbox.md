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
