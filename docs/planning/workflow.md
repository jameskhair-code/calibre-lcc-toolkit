# Development Workflow

How a version cycle runs, end to end. Durable across all v1.x cycles — the
specifics of any one cycle live in its charter under `docs/planning/`, not
here. For the web-vs-local role split, see "The hybrid Claude pattern" in
`CLAUDE.md`; this document is the cycle *loop* that pattern runs inside.

## The cycle loop

Each v1.x cycle moves through five phases, then loops:

### 1. Architect (web Claude)
A strategic re-audit at the version boundary. Pick the next theme, prioritise
candidate items, sanity-check parking-lot promotions, weigh real-library
signal from the cycle that just shipped. Output is a scope brief — items with
motivation, touch points, sizing, risk, dependencies.

### 2. Codify (web Claude → documents)
Translate the brief into the right documents. The per-version charter
(`docs/planning/v1.x-charter.md`) is the contract for the cycle: shipping
order, sequencing notes where items overlap, cut candidates flagged up front.
The charter can be drafted by either surface; `docs/planning/roadmap.md`
updates happen here too if scope shifted.

### 3. Implement (local Claude, in Cursor)
Run the cycle item by item. One PR per item. Smoke-test every user-visible
change against the real Calibre library before merge. Pause after each merge
for review and explicit go-ahead before the next item. L-sized or high-risk
items get a two-phase pause: investigate/measure → report → wait for go-ahead
→ implement. The cycle closes with a release chore: version bump, CHANGELOG,
annotated tag, GitHub Release.

### 4. Capture findings (ad-hoc, any time)
During implementation or any real use, things noticed — bugs, rough edges,
enhancement ideas — go into `docs/planning/inbox.md`. Capture is cheap and
unsorted; no triage at capture time. Add freely. (See "The inbox" below.)

### 5. Re-audit (web Claude)
After the version ships, return to web Claude before spinning up the next
cycle. Read what shipped (the CHANGELOG entry), read the inbox, and:
- Triage and route every inbox entry — into the next cycle, into the
  roadmap's LATER layer (`docs/planning/roadmap.md`) for a later cycle, or
  out as a quick standalone fix.
- Grade the prior plan's accuracy against what actually happened (items
  retracted, cut, re-scoped — and why).
- Shape the next theme.

Then loop back to phase 1. The re-audit *is* the next cycle's architect phase.

## The inbox

`docs/planning/inbox.md` is a standing capture buffer, not tied to any single
version. Lifecycle:
- **Capture (phase 4, any time):** append an entry. Format: one-line title,
  1–2 sentence description, rough area/touch-point, date. A loose "smells like
  vX" hint is welcome but not binding — routing is decided at re-audit.
- **Route (phase 5, every boundary):** web Claude reads the full inbox, and
  with James decides where each entry plugs in. An entry may wait several
  cycles until it clusters naturally with related work.
- **Clear:** routed entries are removed (or marked done); the file persists,
  the contents flow through it.

Capture is cheap, routing is deliberate, the inbox is forever.

## Who commits what

The web/local split is about where the *real environment* lives, not about
ceremony. The rule follows from that:

- **Code → local Claude.** Code changes need real-library smoke tests, and the
  real Calibre library lives on the maintainer's machine. Web Claude cannot
  verify feature correctness, only code correctness.
- **Documentation → either surface.** Charters, planning docs, the inbox, this
  workflow file — all are text with no library dependency and no smoke test.
  Web Claude can create and commit them directly. When it does, it branches off
  current `origin/main` (fetching first), since its working clone may be stale
  relative to what has shipped.
- **Tag refs and GitHub Releases → local only.** The web sandbox blocks
  tag-ref pushes; tag creation and Release publication happen on the
  maintainer's machine.

## Cross-cutting principles

Learned in practice, durable across cycles:
- **Code is ground truth, not the plan.** Charter and plan premises must be
  verified against current code before building. A plan written cycles ago
  describes intent, not reality. (v1.7 item 1 was retracted when the code
  showed LC had already been removed a cycle earlier.)
- **Measure before building.** When an item's value depends on an empirical
  question, probe first and let the data make the ship/cut call. (v1.7 item 2
  was cut when measurement showed no parallelism surface left.)
- **Smoke-test against the real library.** The test suite verifies code
  correctness; only a real-library run verifies feature correctness. Be
  explicit when manual testing wasn't done.
- **Start sessions clean.** `git checkout main && git pull` before any kickoff,
  so work branches off current main and plans read accurate state.
- **Pause at the right gates.** One pause per PR by default; a two-phase pause
  for L-sized or high-risk items so the decision lands before code, not after.
