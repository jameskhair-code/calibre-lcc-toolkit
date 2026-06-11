# Roadmap — forward plan

The single forward-looking planning document. Created at the post-v1.9
re-audit (2026-06-11) by reconstructing
`docs/planning/v2.0-plan-roadmap-construction.md` (now a historical artifact)
and consolidating `ROADMAP.md`'s parking lot (now a historical record of what
shipped through v1.5). One forward document; everything else under
`docs/planning/` is either a per-cycle charter or history.

Two layers, deliberately unequal:

- **NOW/NEXT** — the next cycle. Sharp, premise-verified against current
  code, committed. The per-cycle charter adds shipping order and per-item
  detail.
- **LATER** — themes, not item lists. Explicitly aspirational: a sketch for
  orientation and motivation, not a contract. Re-scoped at every version
  boundary; expect it to drift, and prefer rewriting it over obeying it. The
  old multi-version plan's premises went stale every cycle it drove — twice
  in v1.9 alone. Fixed item lists more than one cycle out do not survive
  contact with the code.

---

## NOW/NEXT — v1.10: Preflight + the first full-library campaign

Charter: `docs/planning/v1.10-charter.md`.

The fork decided at the post-v1.9 re-audit: instead of building the old
plan's six speculative cost/perf/scale items, run the real ~5,000-book
enrichment campaign **now** and let the run pull items in by demonstrated
need. This is the repo's standing measure-before-build lesson applied at
cycle level — four of the old six items depended on measurements that don't
exist, and the campaign produces every one of those measurements as a
by-product of doing the actual job the toolkit was built for.

### Preflight (ships first, as the v1.10.0 release)

Four items, all premise-verified against `main` at the re-audit
(HEAD `d8efc48`):

1. **Title/author rules-audit fixes** (items 1–8 of the 2026-06-10 audit;
   rules-content PR + real-library smoke). Items 1–2 are outright prompt
   defects — defect removal before clean-titles runs at scale.
2. **Price-table + model-alias refresh** (`usage.py:_PRICES` is January-2026
   data; `models.py` resolves `latest` → `claude-opus-4-7`). Includes the
   deliberate "which model runs the campaign" decision with a projected
   campaign cost per candidate.
3. **Manual-flag audit logging** (`db.py` `mark_mqg_complete` /
   `clear_mqg_flag` write no audit entry — the one live correctness gap;
   the campaign generates thousands of flag events whose history would
   otherwise be unreconstructible).
4. **Budget guardrail** (preflight cost projection before each step run;
   the one item from the old v1.10 list that clearly earns a pre-campaign
   slot).

Plus one operational check, no PR: confirm the Anthropic usage-tier bump
(the primary mitigation for the 2026-05-28 429 incident) before the first
full-library wave.

### The campaign

Per-step sweeps across the library in pipeline order, batched to review
stamina, with calibration checks at wave boundaries. Structure, gates, and
the capture ritual are in the charter. The campaign ends when James says it
ends; its findings are the v1.11 re-audit's input.

### The pull-list — built only on demonstrated need

The remaining old-v1.10 items, demoted from "scheduled" to "triggered."
Each is pulled into the campaign (or v1.11) only when its trigger fires;
premises re-verify at pull time.

| Item | Trigger |
|---|---|
| 429-aware pacing in `ai/_client.py` (today: SDK `max_retries` only) | A tier-bumped run still drops batches to 429 |
| Description-cache persistence (`book_description.py` is in-run only; verified unshipped) | Re-runs/regrades at scale repeat description fetches materially |
| Prompt-cache effectiveness alarm (`cache_hit_rate` + `usage.jsonl` baselines already exist) | Hit rate visibly degrades across campaign sessions |
| Memory streaming / chunked rendering | Rich-table collapse or RSS pressure actually observed at campaign batch sizes |
| Per-step latency telemetry | A wave's wallclock can't be attributed between AI / calibredb / catalog |
| Catalog outer-pool worker-cap tuning (v1.7 leftover; pool measured 89.9% saturated at 8) | A full-batch cascade run shows saturation materially below the v1.7 measurement |
| `normalize.py` typographic quotes/ellipsis (rules-audit item 9) | James signs off the mapping — S, can ride any cycle |
| Cosmetic leftovers (3× `_strip_html`; orphaned `IDENTIFIER_TYPES` in `fetcher.py`) | Chore; ride along any convenient PR |

**Demoted to parked:** concurrent multi-step orchestration (the old v1.10
item 6). Its stated dependency (the commands/ migration) now exists, but
there is no demonstrated need, and SQLite's single-writer constraint makes
it the worst risk/value item on the old list.

---

## LATER — themes (aspirational, re-scoped every boundary)

No version numbers on intermediate themes. The destination is fixed; the
route is re-decided at each re-audit on whatever the previous cycle proved.

### The destination — v2.0: A-Z library completeness + UX overhaul

James's vision, and the thing the major-version bump celebrates: every book
fully complete, every tracked dimension green. A full library-landscape
view; tracking *every* aspect of a book A-to-Z, including currently-manual
dimensions (e.g. covers — completion tracked via a flag column even while
editing stays manual); faster menu/button flow; an end-to-end workflow that
makes perfect sense. Builds on existing primitives — the `#mqg_*` completion
and manual-flag columns, `count_books_with_all_columns_true` (`db.py:513`),
the TUI pipeline line — an extension of the completeness model plus a UX
rebuild, not a rewrite. Scoping this is a multi-cycle architect pass in a
web session at the boundary where the campaign has the current five steps
approaching done and "what does *fully complete* mean" becomes the live
question.

### The measurement layer — self-audit & reproducibility

The old plan's "v2.0 flagship," reframed: not a rival to the A-Z vision but
its instrument. A completeness claim at library scale is only trustworthy if
the toolkit can explain its own output. Candidate items (all structurally
unblocked by the v1.8 audit-log reader and the append-only audit schema):
session report, library health index (the completeness dashboard the A-Z
view needs), AI-prompt versioning pinned per write, replay-from-audit-log,
library state snapshot + diff. The campaign will generate the first real
appetite signal for these — "what did yesterday's wave do" stops being
hypothetical.

### Display & polish cluster

Deferred across v1.8/v1.9, clusters naturally into a mini-cycle when
appetite strikes: side-by-side diff view for proposed changes (the shared
review helper it depends on shipped in v1.9), per-step warnings rollup, TUI
since-last-session sidebar (reuses the audit-log reader), TUI selected-step
highlight.

### Quality depth

AI-judgment subject coherence — the successor to v1.8's measured-and-deferred
keyword approach (~70% FP, intrinsic to keyword-matching prose). Ask the
model whether a book's *central* subject warrants a missing tag; likely an
opt-in sweep tool, not inline warnings. Needs its own cost/FP measurement;
the campaign's full-library tag output is better seed data than anything
available today. Related: a consumer for `rule-revisions.jsonl` (capture has
been accumulating since v1.8; nothing reads it yet).

### Parked — promote on evidence

Carried from the consolidated parking lots; each records its promotion
condition.

- **Multi-library support** — promote if a second library appears.
- **Pluggable AI provider** — explicit project decision (Anthropic-only);
  promote only on a material pricing/capability shift.
- **Pipx/installer packaging** — promote if the toolkit ships to others.
- **Browser/web UI** — promote if remote use becomes real.
- **Configurable Rich theme** — solo maintainer, stable terminal; unlikely.
- **`--explain` per suggestion** — largely covered by source-notes +
  provenance panels.
- **Compact/filterable/sticky review tables, quit confirmation, mid-batch
  checkpoint resume, undo-last-session, inline edit during review** — all
  considered and rejected in earlier cycles; promote only on repeated
  real-use friction.
- **Restore LC catalog reachability** — closed as superseded (OL-only since
  v1.3); would need new evidence of OL coverage gaps.
- **Concurrent multi-step orchestration** — demoted from the old v1.10; see
  pull-list note above.
- **Identifier reach for the no-ISBN population** — v1.7 measured ~43% of a
  sample with no usable identifier (pure-AI path); promote if campaign waves
  show identifier-bearing books well-covered and this is the dominant gap.

---

## Maintenance rules

- **Premise-verify before building.** Every NOW/NEXT item is checked against
  current code at charter time; LATER themes are re-verified when promoted.
- **Re-scope LATER at every boundary.** The re-audit (workflow phase 5)
  rewrites this file's LATER layer freely; only NOW/NEXT is a commitment.
- **Capture flows through the inbox** (`docs/planning/inbox.md`), routing
  happens here at boundaries, per `docs/planning/workflow.md`.
