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
- *Fixed 2026-06-09* (`fix/unflag-manual-requeue`): `clear_mqg_flag` now
  deletes the row; full decline → flag → unflag → re-queue loop verified on
  the real library. Library measurement found zero stale 0-rows, so no data
  migration was needed. **Still open from this entry:** manual-flag writes
  are not audit-logged (flag history can't be reconstructed) — route at the
  re-audit.

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

**Title/Author rules audit — fixes and improvements for
`rules/author_title.md` and its prompt wrappers.** Requested deep dive
(web session, 2026-06-10). Findings, in priority order:

1. *Contradictory example in T-SER-02* (`rules/author_title.md:289`): the
   WRONG line shows the **correct** transformation — `"Eon (The Way Book 1)"
   → "Eon"` — and the RIGHT line on 290 is byte-identical. The WRONG line
   was clearly meant to show the *unchanged* title (the "[leaving unchanged
   is also wrong]" note confirms the intent). As written it tells the model
   the correct answer is wrong. Fix: WRONG example → `"Eon (The Way Book 1)"`
   unchanged.
2. *Duplicated alternative in T-SUB-07* (`rules/author_title.md:234`):
   `separated by " / " (or " / ")` — both strings are byte-identical
   (verified via hexdump). Probably meant a non-spaced `"/"` as the
   alternative. Fix or drop the parenthetical.
3. *GEN-01 conflicts with the output format*: GEN-01 says note
   `"No changes needed."` on unchanged rows; `author_title_output_format.md`
   says write `"Already correctly formatted."` and **never** write "No
   changes needed". The prompt argues with itself. Code tolerates both
   (`ai/authors.py:128`), so this is prompt-only: align GEN-01 (and the
   GEN-07 examples) to "Already correctly formatted."
4. *GEN-07 vs output-format notes style*: output format wants rule-ID
   citations ("Removed generic subtitle per T-SUB-02"); GEN-07's examples
   cite no rules. Harmonize on the rule-citation style — it makes review
   and calibration traceable.
5. *A-MUL section assumes a single-string author field*, but the output
   schema is a JSON array (one element per author). " & " separators are a
   display concern; the model should never need them. Add a bridge note to
   A-MUL: each `authors` array element is exactly one person; never put
   "&" inside an element except corporate names (A-ROL-11 / A-SPE-07).
   Code-side fallback: `ai/authors.py:110` splits returned strings on ";"
   but not on " & " or " and " — consider extending the split if mis-packed
   elements show up in practice.
6. *A-MUL-05 condition oddity*: "more than three authors AND contains
   'et al.'" — the flag should trigger on "et al." alone.
7. *T-CAP-10's stylistic-lowercase example is an author, not a title*
   ("bell hooks — author name, not title" — the rule is about titles).
   Replace with a real lowercase-title example or drop the parenthetical.
8. *`rules/confidence.md` SECTION CONF index omits author_title.md*
   (lists lcc/comments/tags/tags_cleanup only). One-line fix: note that
   author/title confidence guidance lives in GEN-02..05.
9. *Code-side candidate (separate small PR)*: `normalize.py` Americanizes
   dashes and diacritics but not typographic quotes/apostrophes
   (`’ ‘ “ ”` → `' "`) or the ellipsis char (`…` → `...`), despite the
   stated plain-ASCII intent — curly apostrophes are common in titles
   ("Where’d You Go, Bernadette"). Add to `normalize_text` + a T-FMT rule
   mirroring the dash treatment, with `test_normalize.py` coverage. Needs
   James's sign-off on the mapping before landing.

Items 1–8 are a single docs/rules PR (no code). All are prompt-content
changes → per the test ritual they need a small real-library smoke run
before being declared done; pytest alone can't verify prompt behaviour.
Items 1–2 are outright defects worth pulling forward. Requested by James
2026-06-10 (web session research; explicit intent — don't drop silently
at re-audit).

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
