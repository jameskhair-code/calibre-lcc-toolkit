# Inbox — untriaged observations

Standing capture buffer for ideas noticed during real use. Not tied to any
single version. Entries are triaged and routed to a specific cycle (or the
ROADMAP parking lot) at each post-release re-audit, then cleared. Add freely;
routing is decided at version boundaries. See `docs/planning/workflow.md`
(phases 4–5) for the full lifecycle.

---

**`unflag-manual` doesn't actually re-queue books — `clear_mqg_flag` writes
0 instead of deleting the row.** Discovered during the v1.9 item-2 real-library
smoke. On this Calibre version, bool-column search `#col:true` matches any
*defined* value (0 or 1) and `#col:false` matches *undefined* — `:yes`/`:checked`
are the value tests. `db.clear_mqg_flag` writes `value=0`, which still matches
`#col:true`, so the steps' `not #<manual>:true` exclusion keeps "unflagged"
books out of every subsequent run: the command's whole purpose (re-queueing)
silently fails. Fix: DELETE the row (restore the undefined state) instead of
writing 0 — and audit the toolkit for other `:true`/`:false` searches that
assume value semantics. Related observation: manual-flag writes
(`mark_mqg_complete` on the `*_manual` columns) are not audit-logged, so
flag history can't be reconstructed. Touch points: `db.py:clear_mqg_flag`,
`commands/unflag_manual.py`, possibly `regrade.py`'s `{manual}:true` check.
Pre-existing (since v1.1-era code), not introduced by the v1.9 refactors.
Surfaced 2026-06-09.

**TUI: highlight the selected pipeline step in the left panel.** The active
step shows in the right detail panel but the left ListView rows have no clear
selected-state treatment — hard to confirm focus at a glance when navigating
with arrows or digit-jumps. Display-only CSS change in `tui/app.py`
(`StepItem` highlighted/focused styling). Low risk. Pairs with v1.8 item 8
(both touch the TUI render path). Surfaced from real use 2026-05-28.
- *Routed 2026-05-29 (post-v1.8 re-audit):* held for a later TUI/polish pass,
  not v1.9 (a pure-refactor cycle takes no display-layer features). Clusters
  with the deferred v1.8 items 7 (warnings rollup) and 8 (since-last-session
  sidebar) and the v2.0-plan diff-view item — all display-layer.

**`clean-titles` 429 rate-limit on large runs.** A 500-book run (50 batches,
5 in flight) hit the org's 8,000-output-tokens-per-minute cap; 1 of 50
batches failed with HTTP 429. Handled gracefully (failed-batch books not
marked complete; re-run retries them) but a clean large run shouldn't drop a
batch. Consider a 429-aware backoff that paces rather than just retries, or
throttling concurrency / batch-size when output-tokens-per-minute is the
binding limit. Likely affects all AI-suggest steps, not just clean-titles.
Touch points: `ai.py` `_run_batches_concurrent` / the retry path. Smells like
v1.10 (cost/perf) unless it recurs often. Surfaced from real use 2026-05-28.
- *Update 2026-05-29:* an Anthropic Console email confirmed this is recurring,
  not a fluke — the org exceeded its Sonnet rate limit **65 times in 24h**
  during the heavy testing day. This is the *current usage tier's* ceiling
  (8k output-tokens/min), not a code bug. Primary mitigation is operational:
  bump the usage tier (auto-advances past $40 in total credit purchases,
  raising limits across all models immediately) — necessary anyway for real
  5,000-book enrichment runs. The code-side pacing/backoff above is the
  *secondary* fix for runs that exceed even the higher tier; it makes the tool
  well-behaved at any tier but is no longer the primary lever. Keep at v1.10.
- *Routed 2026-05-29 (post-v1.8 re-audit):* confirmed → v1.10 (cost/perf
  cycle). Operational mitigation (tier bump) is primary; code-side pacing is
  the secondary lever, scoped there.

**Consolidate the two parking lots.** Two parking lots currently coexist:
`ROADMAP.md`'s "Beyond v1.5" section and the parking lot in
`docs/planning/v2.0-plan-roadmap-construction.md`. `ROADMAP.md` is now mostly
historical — items 1–22, nearly all shipped through v1.5 — and the v2.0 plan
has largely superseded it as the forward-looking roadmap. Converge to one
forward parking lot (likely the v2.0 plan's) and demote `ROADMAP.md` to a
historical "what shipped through v1.5" record. Docs-only; small standalone
PR; doesn't block any cycle. Surfaced 2026-05-28 (process simplification).
- *Routed 2026-05-29 (post-v1.8 re-audit):* remains a standalone docs PR, any
  time; blocks nothing. Noted in the v1.9 charter's parking-lot delta.

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
- *Routed 2026-05-29 (post-v1.8 re-audit):* stays parked → v1.9+/v2.0. Not
  v1.9 (a pure-refactor cycle adds no AI behaviour). Needs its own cost/FP
  measurement before it earns a slot; the Phase A seed data above carries.

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
- *Routed 2026-05-29 (post-v1.8 re-audit):* unchanged — a pointer, scoped at
  the post-v2.0 boundary. Not a v1.9 item.
