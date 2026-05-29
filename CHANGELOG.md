# Changelog

---

## v1.8 — Calibration Action Loop

Per-version charter: `docs/planning/v1.8-charter.md`. Seven core items scoped. Six PRs shipped (#52, #53, #54, #55, #56, #57); one item (subject coherence) attempted, measured, and deferred; three display-layer items deferred up front. Test suite from 528 → 581 hermetic tests.

The v1.8 theme is turning the v1.4 measurement loop into an **action loop**. Since v1.4, `audit-confidence` could *show* when a confidence tier drifts from observed accuracy, but acting on what it showed was manual or impossible. This cycle closes that gap: reduce first-run friction, surface calibration trends across sessions, capture rule-edit intent at the moment of friction, make the audit log queryable, gate the one AI change class that can silently corrupt data (authorship), and — the spine — re-grade stale writes after a rule changes. The one coherence-depth item (subject-level coherence) was the cycle's high-risk bet; it was prototyped, measured against the real library, and deferred on the evidence.

Two of the seven items carried a mandatory two-phase pause (prototype/measure → report → go-ahead → build): the re-grade workflow (shipped) and subject coherence (deferred).

### Items shipped

**Item 2 — audit-confidence first-run friction reduction** (PR #52)
- The calibration command's first run on a fresh library was the highest-friction: it asked for a large initial sample before showing anything useful. Reduced the default initial sample to 5/tier, ordered grading high-tier-first (`_TIER_PRIORITY`), and surfaced an interim per-(step, tier) trajectory after a handful of grades rather than only at session end (`commands/audit.py`). Signal now accrues before the session is over.

**Item 3 — Calibration trajectory visualization** (PR #53)
- Multi-session calibration data accumulates in `~/.calibre-toolkit/calibration.jsonl`, but there was no view of whether a tier is getting more accurate over time. New `audit-trajectory` command renders a per-(step, tier) Unicode-block sparkline with first/latest strict precision and the change between them, high-tier-first, latest value coloured against the most recent threshold (`commands/audit.py`: `load_calibration_sessions`, `build_trajectories`, `_render_trajectory`, `run_trajectory`). Purely observational — reads one file, writes nothing.

**Item 5 — Per-tier rule-edit prompts** (PR #54)
- When `audit-confidence` flags a tier whose strict precision dropped below threshold, session-end now prompts "what would you change in the rule?" and appends the captured intent to `~/.calibre-toolkit/rule-revisions.jsonl` (`persist_rule_revisions`, `_prompt_rule_revisions`). A capture buffer of accumulated signal for a future architect pass — nothing reads it automatically yet.

**Item 6 — Audit-log query CLI** (PR #55)
- The audit log (`~/.calibre-toolkit/audit.log`, JSONL since v1.1) was grep-only. New read-only `audit-log` command renders matching entries as a compact Rich table with `--field` / `--book-id` / `--step` / `--since` filters (AND semantics) and a `--limit` recent-window (default 50). Opens one file, writes nothing.
- **Charter deviation, recorded:** the charter named a `--session` filter, but the audit log carries **no session marker** — the writer (`logging_config.py`) emits `timestamp/book_id/field/new_value/confidence/source/step` plus per-write extras, never a session id. `--step` (the grouping the data actually has) was substituted and documented in the command's help. Shipped as a flat `audit-log` command rather than `audit-log show`, matching the repo's existing `audit-*` command style.
- **Enabler for the re-grade item.** Extracted the canonical low-level reader (`read_audit_entries`) and filter (`filter_entries`) into `commands/audit_log.py` so there is exactly one audit-log parser. Calibration's `load_audit_records` now builds on it instead of re-opening the file; the re-grade workflow reuses it.

**Inbox item — Author-change review gating** (PR #56)
- From the 500-book `clean-titles` run (2026-05-28): the AI removed a real co-author from "J R" (Joy Williams & William Gaddis → William Gaddis only) on its own training knowledge, marked it medium confidence, and it auto-applied under "apply all." Authorship deletions from model memory are a high-risk class that can silently corrupt data.
- `CleanupSuggestion.removes_author` detects an author drop or substitution via a normalization-aware key (diacritic-, case-, punctuation-, order-insensitive, built on `remove_diacritics`), so legitimate fixes (capitalisation, García → Garcia, "Williams, Joy" → "Joy Williams") are **not** flagged. Removals are capped to low confidence and review-only (`modules/authors.py`: `_gate_author_removals`): they fall out of every auto-apply path (`--auto-apply-high`, high-only, and the bulk "all" branch, which now routes them through per-book review) and are flagged red in the review table and prompt. Confidence semantics change for one field class only; legitimate author fixes flow through unblocked (confirmed on the real library).

**Item 4 — Re-grade workflow** (PR #57, two-phase)
- When you edit a rule (e.g. `rules/lcc.md`) to fix a calibration miss, every AI write made before that edit is stale relative to the new rule. New `regrade --step <step> --before <date>` finds the affected books and re-runs just those against the current prompt, reusing each step's existing review/apply flow with an explicit book-id list (`commands/regrade.py`, `db.search_by_ids`, `book_ids` params on the lcc/comments/tags run functions). Scope: the three audited, rule-driven steps — lcc-enrich, comments-enrich, tags-enrich. (clean-titles and enrich-identifiers write no audit trail, so their stale books can't be found this way — see limitations.)
- **Staleness keys off a timestamp cutoff, not a session** — the audit log has no session marker. A book is stale when its *latest* audit entry for the step predates `--before`; the selector aggregates to latest-per-book, so a book already re-graded after the cutoff drops out (no double re-grading). Built on item 6's reader — no second parser.
- **Re-grade audit-entry semantics (per charter DoD):** the run executes inside a `regrade_audit(cutoff)` context (`logging_config.py`) so every resulting audit entry is tagged `regrade=<cutoff>` at the single `audit_log` choke point — guaranteeing no fan-out write escapes the marker. Marked entries are **excluded from calibration** (`load_audit_records`) so a re-run against a changed rule doesn't mix pre/post-change accuracy in the same tier stats. (Calibrating re-grades as a separate cohort was considered and deferred.) The marker uses a `ContextVar`, which is correct because the three audited apply paths write on the main thread (sequential `for` loops); a load-bearing guard comment and a regression test (`test_marker_lands_through_real_apply_paths`) fail if any of those loops is ever moved onto a thread pool, where the ContextVar would silently drop.
- **Manual flags respected:** re-grade bypasses Calibre search, so it re-applies the steps' `not <manual>:true` exclusion itself via the id path — manually-curated books are skipped by default; `--force` includes them. Proven on the real library (45 flagged books correctly skipped). The `book_ids` run path also bypasses the already-populated skip, since the explicit list is authoritative.

### Item attempted, measured, and deferred

**Item 1 — Subject coherence checking** — prototyped, measured, deferred (not shipped, not even opt-in)
- The goal was to extend `coherence.py` from period-only to subject-level ("the comment discusses jazz but no jazz tag"), shipping opt-in-first and promoting to default only if the real-library false-positive rate proved low enough to trust. Designed precision-first: high-bar, low-recall, fire only when nearly certain.
- **Phase A measurement (the decision driver):** a `check_subject_coherence` prototype with a curated 15-subject keyword map (Slavery, Holocaust, Jazz, Espionage, Civil Rights, Pandemic, …), reusing the production matchers, was run against the real batch of **4,428 books that have both comments and tags**. It fired 499 times across 458 books (10.3% of the batch). A classified sample put the **false-positive rate at ~70%**, and crucially the FPs are **intrinsic to keyword-matching prose**, not fixable map gaps: metaphor/idiom ("a *chess game* of a novel", "an *epidemic* of loneliness", "*Boxing* Day"), incidental mention (a character's job/hobby; theme litanies), comparison ("rivaled only by the *Holocaust*"), and blurb boilerplate. Only ~15% of FPs were the fixable kind (book adequately tagged under a variant not in the map); strip those and the intrinsic FP rate is still ~60%. Even the best subjects (Slavery, Holocaust) missed the "nearly certain" bar at ~25–35% FP.
- **Disposition: deferred.** ~70% FP fails the charter's "fire only when nearly certain"; shipping it even opt-in would risk eroding trust in the period checks that *do* work. This confirms the v1.4 reasoning that excluded subjects from `coherence.py` in the first place ("too many ways for a comment to discuss a thing without it deserving a tag"). The keyword approach is the wrong tool, not a tuning problem.
- **Candidate future direction:** AI-judgment-based subject coherence (ask the model whether the prose's central subject is reflected in the tags), not keyword matching. That would need its own cost/FP measurement before adoption. No follow-up scheduled; this disposition is the record.

### Deferred this cycle (decided up front)

Held back from the v2.0 plan's v1.8 section and the inbox to keep the cycle on its action-loop spine — not cut, parked for a lighter follow-on (per the charter's "Deferred this cycle" section):

- **v1.8 item 7 — Per-step warnings rollup** (S, display-layer).
- **v1.8 item 8 — TUI since-last-session sidebar** (M, display-layer; would reuse item 6's audit-log reader).
- **Inbox: TUI selected-step highlight** (pairs with item 8).

These cluster naturally (all `tui/app.py` / display-layer) and could ride a polish mini-cycle if appetite remains.

### Known limitations after v1.8

- **Re-grade covers lcc/comments/tags only.** clean-titles and enrich-identifiers write no audit trail (only lcc/comments/tags call `audit_log`), so re-grade can't find their stale books. A cheap future add would be to give clean-titles an audit trail first; enrich-identifiers is web-lookup, not rule-driven, so it's a poorer fit.
- **The re-grade marker relies on main-thread apply.** The `ContextVar` design is correct today and guarded by a regression test, but it is a deliberate constraint, not a free property — see the guard comments in `logging_config.py` and `db.apply_metadata_batch`.
- **Subject coherence remains period-only.** No subject-level coherence shipped; the period checks (`_PERIOD_KEYWORDS`) are unchanged. Revisiting requires the AI-judgment approach above, with its own measurement.

---

## v1.7 — Catalog Reach, Take 2

Per-version charter: `docs/planning/v1.7-charter.md`. Seven items allocated in the v2.0 multi-version roadmap (`docs/planning/v2.0-plan-roadmap-construction.md:206-331`). Five PRs shipped (#41, #43, #44, #45, #46), one item retracted as superseded in v1.3, one item cut after measurement. Test suite from 444 → 528 hermetic tests.

The v1.7 theme is "exploit the Open Library fallback for everything it can do, now that LC is permanently out of the picture." Two tracks shipped: OL-cascade speedups that compound (items 3 and 4) and catalog-shape items that tighten what the toolkit writes when the cascade hits or misses (items 6, 5, 7). This was a catalog cycle, not an AI prompt cycle — the one AI-touching addition is item 5's summary-only call; item 6 changes a write-time truncation rule; item 7 is display-only. No new commands, no architectural refactors.

Two non-PR dispositions called out in the theme:

- **Item 1 — Resolve item 12a (LC Cloudflare workaround)** — retracted as superseded in v1.3. The original charter (PR #39) inherited the v2.0 plan's mis-framing of LC as "dormant since v1.3" when the actual state was "removed in v1.3." Verified against `docs/LC-Cloudflare-Investigation.md` and `calibre_toolkit/services/lc_catalog.py:1-41`: the LC code paths were deleted in v1.3 and the module has been OL-only on `main` since. PR #40 corrected the charter and re-anchored items 5/6/7 to the live OL-only world (collapsing the conditional "if LC kept / if LC dropped" trees the original charter carried).
- **Item 2 — In-cascade request parallelism** — cut after item-3 measurement (PR #42). The probe ran against a 30-book real-library sample after PR #41 merged. Inside one book's cascade, the four phases (D direct, W work-key, E editions, B batched bibkeys) are strictly data-dependent — item 3 eliminated the only fan-out point. Cross-book parallelism is already 89.9% saturated by the existing 8-worker outer pool (`modules/lcc.py:_catalog_lookup_batch`). The longest-pole book caps end-to-end wallclock at ~15 s even at infinite parallelism. The in-cascade `ThreadPoolExecutor` item 2 was scoped for has no surface left to win on. Outer-pool worker-cap tuning is recorded as a v1.10 follow-up candidate.

### Items shipped

**3. Batch sibling-ISBN classification lookups** (PR #41)
- The OL edition cascade used to issue one `/api/books?bibkeys=ISBN:X` request per sibling — up to 10 sequential HTTP calls per cascading book once the sibling cap was raised to 10 in v1.3. Collapsed into a single `/api/books?bibkeys=ISBN:A,ISBN:B,...,ISBN:J` request that returns a dict keyed by `ISBN:{i}`. Same endpoint, one call instead of N.
- Premise verified against OL before code (Phase A probe): the original charter wording proposed switching to `/works/{key}/editions.json`, but that endpoint is already called by the cascade and empirically does not carry `classifications` per edition (0/50 on `/works/OL39396W`, 0/1 on `/works/OL28591899W`). The batched bibkeys request was the actual achievable win — PR #40's charter patch corrected the item-3 framing accordingly.
- New private `_lookup_isbns_openlibrary_batch(isbns) -> dict[input_isbn, Optional[CatalogHit]]` in `services/lc_catalog.py`. `lookup_by_isbn_openlibrary` now delegates to it with a single-element list so both single-call and cascade paths share one response parser — no drift risk if OL changes the record shape. Sibling preference order, first-hit-wins semantics, source-string format, and the 10-ISBN cascade cap are unchanged.

**4. Cross-run work-key cache persistence** (PR #43)
- Resolving "this ISBN belongs to OL work XYZ" is stable across runs but pre-v1.7 had no cache at all — every fresh run re-fetched `/isbn/{isbn}.json` for every cascading book at ~3.5 s per call (the single largest phase of the cascade, per item 2's measurement). Now persisted to `~/.calibre-toolkit/ol-workkey-cache.json` with a 90-day TTL; subsequent runs skip the lookup entirely for ISBNs already resolved (positive or negative).
- File schema: `{"version": 1, "entries": {<cleaned_isbn>: {"work_key": str|None, "fetched_at": ISO8601 UTC}}}`. Lazy load on first lookup; atomic write (write-temp-then-rename) on every store; one lock guards both dict and file IO. Corrupt files, unknown schema versions, and missing files all degrade to "empty cache, repopulate on miss" with a warning log — never breaks the catalog lookup path.
- Both outcomes cached: positive (work key returned) and negative (OL responded but had no `works` field, OR responded 404). To distinguish definite 404 ("safe to cache") from transient failure (don't cache), `_http_get_json` gained a `treat_4xx_as_empty: bool = False` parameter. When True, definitive 4xx returns `{}` instead of `None`. `_ol_work_key_for_isbn` opts in; existing callers unaffected.
- Env override `CALIBRE_TOOLKIT_OL_WORKKEY_CACHE` (used by the test suite to redirect each test to `tmp_path`). New `reset_workkey_cache()` test helper drops in-memory mirror and deletes the cache file.
- Concrete impact (30-book real-library smoke, cold → warm): W (work-key) phase per call drops from 3525 ms to **0 ms** (cache hits cleanly); per-cascading-book wallclock drops by ~3 s; total wallclock 26.8 s → 24.5 s (-8.5%). End-to-end wallclock savings are smaller than per-book savings because the 8-worker outer pool was already 89% saturated and the longest-pole book caps the floor. On multi-day-spread runs the cache compounds: every previously-seen ISBN stays free within the 90-day TTL window.

**6. AI-only `lcc` truncation** (PR #44)
- A v1.6 real-library run surfaced AI Cutters that were structurally wrong for the author's surname (e.g. `PS3603.O773` proposed for "Correia", whose Cutter lives in the `C6…` range). The class letters are nearly always right — they come straight out of standard LC subject schedules — but the Cutter and date are educated guesses the AI cannot verify without catalog access.
- When the OL cascade returns no hit, the structured `lcc` field is now truncated to the class portion only (class letters + class number, e.g. `PS3603`, preserving any decimal subdivision such as `PR9619.3`). `lcc_summary` is preserved verbatim — the AI's full reasoning still lives there. Catalog-sourced suggestions are unchanged: their Cutter/date strings come from member-library cataloging in OL, not the AI.
- Implementation: `_truncate_to_class_portion(call_number)` regex slice + `_truncate_ai_only_lcc(suggestions)` in-place batch helper in `modules/lcc.py`. Filter key is `LccSuggestion.source_authority == "ai_inference"`. Single wiring point right after `ai.suggest_lcc(...)` returns. No prompt change — the slice gets us where the charter wanted without paying a prompt-rewrite tax.
- Documented in `docs/LC-Cloudflare-Investigation.md` under the Resolution section.

**5. Description-grounded summaries on OL catalog hits** (PR #45)
- When a book has both an OL catalog hit AND a pre-fetched description, one batched summary-only AI call replaces the terse template summary ("Classified by Open Library under PR — English Literature.") with description-grounded prose. The catalog-derived `lcc` / `lcc_primary_class` / `lcc_secondary_class` fields are not touched — only `lcc_summary` is rewritten. Best of both paths: catalog trust on the class fields plus library-jacket prose on the summary.
- New `AIClient.suggest_lcc_summary(books, catalog_context_map, description_map) -> dict[book_id, prose]`. Batched (default 10). Empty AI responses (identity-mismatch signal) are filtered out — the dict only contains books the caller should overwrite. New focused prompt files under `rules/lcc_summary*` (smaller than reusing `rules/lcc.md` — the summary-only flow doesn't need confidence/source/SRC rules). New `LccSummaryItem` schema with `{id, lcc_summary}`.
- Description prefetch widened from `ai_books` only to ALL books with ISBNs; both the existing item-11 AI flow and the new summary-only flow read from one shared `description_map`.
- Books without a description, identity-mismatch rows, and AI batch failures all silently fall back to the catalog-template summary. New `_apply_ai_summary_to_catalog_hits` in `modules/lcc.py` handles all three fallback paths.
- **Cost-watch result (per charter):** 30-book real-library smoke, $0.0024 per OL-hit book (17/17 conversion when description available; +$0.04 versus the item-6 baseline of $0.13). Extrapolated to a full 5000-book library run that's roughly +$3–4 incremental for the prose-summary uplift. Verdict: ship unchanged — well within charter bounds, no prompt narrowing or trigger restriction needed.

**7. Catalog-source provenance in summary panel** (PR #46)
- The lcc-enrich end-of-run panel now carries a `By source:` row showing OL direct / OL cascade / AI-only counts as discrete contributions. Re-uses `StepSummary.extras` (no schema change — already designed for per-step breakdowns; comments uses extras for word count, identifiers for `by_lookup_method`). Zero rows are dropped so a 100%-OL run doesn't print `AI-only: 0`.
- Display only — no new commands, no cost change, no AI calls. Pipeline internals unchanged: counts come from `cat_stats` (already tracked by the cascade) and `len(ai_suggestions)`.
- Ship vs cut (per charter cut criterion: "cut if the breakdown turns out not to carry signal the existing one-line diagnostic in `lcc.py` already conveys legibly"). Decision: ship — the mid-run diagnostic shows OL direct and OL cascade hits but NOT the AI-only count; the panel row surfaces all three sources in one persistent place that survives diagnostic-format changes and mirrors the identifiers panel's `by_lookup_method` convention.

### Known limitations after v1.7

- **Books without an ISBN remain pure AI.** Items 4 and 5 both require an ISBN to do their work — the work-key cache is keyed by ISBN, and the description prefetch goes through Google Books / Open Library by ISBN. A book with no usable identifier never gets a catalog hit and never gets a pre-fetched description; it falls through to the standard AI path with the item-6 truncation applied to the result. The v1.6 30-book sample showed ~43% of books in this category (13 of 30). Improving identifier reach is out of scope for v1.7 and not in the v2.0 plan beyond what's already in `enrich-identifiers`; surface as a future parking-lot candidate if real-library v1.7 results show identifier-bearing books are now well-covered and the no-identifier population is the dominant remaining gap.
- **LC stays gone.** Item 12a was closed as superseded in v1.3 and the v1.7 charter retracted the planned item 1 re-investigation accordingly. Restoring LC reachability would be net-new work (re-writing the LC paths from scratch using `curl_cffi`, OAI-PMH, or bulk MARC dumps); the historical investigation context is preserved in `docs/LC-Cloudflare-Investigation.md`. A future cycle would need new evidence — e.g. OL coverage gaps that LC would close — to motivate revisiting.
- **Outer-pool worker cap (`_CATALOG_LOOKUP_WORKERS = 8`) untouched.** Item 2's measurement showed the pool already 89.9% saturated at 8 workers, with the longest-pole book capping end-to-end wallclock at ~15 s even at infinite parallelism. A worker-count tuning change (8 → 12, say) might recover most of the remaining headroom but is a one-line cap bump, not the in-cascade parallelism item 2 was scoped for. Recorded in the v1.7 charter's *Out of scope* section as a v1.10 follow-up candidate, surfaceable sooner if a larger-sample run warrants.

---

## v1.6 — Release-week follow-ups & console polish

Per-version charter: `docs/planning/v1.6-charter.md`. Nine items in scope from the v2.0 multi-version roadmap (`docs/planning/v2.0-plan-roadmap-construction.md`). Seven PRs shipped (#32, #33, #34, #35, #36, #37, plus PR #30 rolled in retroactively), one item cut. Test suite from 444 → 450 hermetic tests.

The v1.6 theme is "small polish to the existing layout" — not the refactor cycle. v1.9 (commands/ migration + shared review-prompt helper) will consolidate many of the touch points v1.6 polished; v1.6's edits were deliberately shaped to be cheap to migrate forward once that refactor lands. Eight of the nine items were S-sized; one was M (the TUI cross-step pipeline line). No AI prompt edits, no new commands, no architectural refactors.

### Items shipped

**PR #30 — Windows console utf-8 fix** (released retroactively in v1.6)
- Merged on `main` after v1.5.0 shipped but before v1.6 began. The post-v1.5 triage memo (`docs/planning/post-v1.5-triage.md`) discovered that `calibre-toolkit clean-titles --help` crashed with `UnicodeEncodeError` on the legacy Windows cp1252 console because typer's Rich help renderer emits a `→` character. `cli.py:13-30` reconfigures stdout/stderr to utf-8 with `errors="replace"` on win32 before any Rich Console is constructed.
- Rolled into v1.6 rather than shipped as a v1.5.1 patch — patch-release discipline doesn't earn its keep on a single-user project, and the fix has been functionally in service via `main` for the whole cycle.

**3. `--dry-run` wiring + flag-standardisation sweep** (PR #32)
- The v1.1 standardisation header at `cli.py:35-49` listed `--dry-run` as a canonical flag, but `clean-titles` never had the wiring added. The post-v1.5 triage spotted the gap. Wired `--dry-run` into `clean-titles` and added the dry-run branch to `run_cleanup` in `modules/authors.py` (mirrors the `lcc-enrich` / `tags-enrich` / `comments-enrich` dry-run path: build the review table, render the cyan dry-run summary panel, return before the apply prompt).
- Audited the full canonical set across every `@app.command()`. The only true gap was `clean-titles --dry-run`. Other "missing" canonical flags on `enrich-identifiers`, `tags-enrich`, `comments-enrich`, `clean-identifiers` are by design — different review patterns or no clear dry-run semantics for the operation those commands perform.
- Latent bug fixed along the way: the "everything looks good — no changes needed" early-exit in `run_cleanup` called `_mark_complete` unconditionally, which would have written the MQG-complete marker even under `--dry-run`. Guarded with `if not dry_run`.

**2 + 6. Prompt discoverability + single-letter shortcuts** (PR #33 — combined)
- Items 2 and 6 both touched the same `Prompt.ask` blocks across the five AI-suggest modules. Combined into one PR per the charter to avoid touching the same five files twice.
- Item 2: a one-line `[dim]Waiting for input…[/dim]` hint now prints immediately before each post-AI-batch bulk-tier prompt. Closes the "screen-goes-blank-then-hangs" failure mode the triage memo documented (the transient progress bar clears on completion, the `Apply changes?` prompt visually disappears).
- Item 6: every bulk-tier prompt now accepts the first letter (`a`/`h`/`r`/`s`/`e`) in addition to the full word. Letters render inline in `\[bracketed]` form so the shortcut is visible without `--help`. Word forms keep working; default behaviour on Enter is unchanged. 13 prompts across 6 modules (`authors.py`, `lcc.py`, `comments.py`, `tags.py`, `identifiers.py`, `clean_identifiers.py`). Each site does the alias normalisation inline with a small dict so v1.9's shared review helper can collapse them all in one move.
- Bug caught during smoke testing: Rich's markup parser consumed `[a]` / `[h]` / `[r]` / `[s]` as style tags, eating the letters from the label (rendered as `ll / igh-only / eview / kip`). Escaped to `\\[a]ll / \\[h]igh-only / …` so Rich emits literal brackets.

**8. Bulk-apply confirmation above threshold** (PR #34)
- When the user picks "apply all" on a batch larger than `review.apply_confirm_threshold` (default 20), a one-line `About to apply to N books. Proceed? [y/N]` confirmation fires before writing. Default `n` so an accidental Enter is safe.
- New tiny shared helper at `calibre_toolkit/review_prompts.py` (one function, `confirm_bulk_apply(n, threshold, console)`). Below-threshold batches short-circuit to True without prompting. v1.9 item 5 will fold the existing duplicated per-tier `Prompt.ask` blocks into the same module.
- 12 "all" branches wrapped across the five AI-suggest modules. `--auto-apply-high` paths deliberately unchanged — the flag's whole purpose is to skip the prompt. `tags-cleanup` pattern-group prompts and `clean-identifiers` are out of scope (different review flows).
- New config knob `review.apply_confirm_threshold` in `config.example.json`, in its own top-level `review` block to match the v1.9 module name. Set very large to disable.

**7. TUI digit/letter jump shortcuts** (PR #35)
- Seven new `Binding` entries plus one `action_jump(idx)` method in `tui/app.py`. `1`-`5` jump directly to MQG steps 01-05, `m` highlights the Maintenance section header, `t` jumps to Tags Cleanup. Faster than arrow-keying through the step list, particularly when returning to a step you know.
- All hidden from the footer (`show=False`) to keep it readable — same convention as the existing `j`/`k` vim-style nav. The "01"-"05" badges already on each step row are the discoverability hook.

**4. TUI cross-step pipeline summary line** (PR #36)
- Replaces the dead `MQG Pipeline` header at the top of the TUI with `Pipeline: 1✓ 2◐ 3◐ 4○ 5○  ·  N/M books fully enriched`. The icon row (`✓` green = all done · `◐` yellow = some done · `○` = none) is a compact digest of per-step progress; the `N/M fully enriched` count is the new signal — the cross-step intersection no per-step row in the left panel can show.
- This is the shape rescued from the v1.5 item 22 rejection memo, which warned that any top-of-screen pipeline view must add information the left panel cannot. v1.6 item 4 passes that test: the icons are derivable, but the fully-enriched count is not.
- New `db.count_books_with_all_columns_true(labels)` SQLite method does the cross-step intersection in one query. Missing column returns 0 (a book cannot be "fully complete" against an undefined gate). Gate labels come from the numbered steps in `_build_steps` so column-name overrides in `config.json` flow through automatically. 6 new hermetic tests cover single column, two- and three-column intersect, the `'#'`-prefix-optional convention, missing column, and empty labels.

**9. `Examples:` epilog on every command's `--help`** (PR #37)
- Moves the existing in-docstring `Examples:` blocks from 11 commands into typer's `epilog=` parameter so they consistently render at the bottom of `--help` (after Arguments + Options), and adds new Examples blocks for the 4 commands that had none (`library-info`, `doctor`, `init`, `setup-columns`). 15 commands × 2-4 example invocations each.
- The shift in render order: Examples were previously buried mid-help, above the Options table. They now appear at the bottom — the standard CLI convention, easier to scan when you remember roughly what you want but not the exact flag syntax.
- The `_TIER_DEFAULTS_HELP` block appended via `__doc__` mutation (for the AI-suggest commands) stays in the docstring — it describes behaviour (per-tier review defaults), not usage.

### Items cut

**5. Summary panel coverage for `tags-review` and `clean-identifiers`** — cut
- v1.5 item 19 deliberately skipped these two commands when shipping the structured `StepSummary` panel: `tags-review` is per-book interactive, `clean-identifiers` is a fix-up utility rather than a batch enrichment, and the panel shape didn't naturally fit either. The v1.6 charter flagged item 5 as a cut candidate to revisit after a cycle of using the panels on the other six commands.
- Decision: keep the original v1.5 reasoning. The per-book and fix-up shapes still don't have a natural fit for `StepSummary`; forcing them in would either duplicate existing per-book/per-fix output or invent fields that don't match the data. No follow-up scheduled; the parking-lot entry in `docs/planning/v2.0-plan-roadmap-construction.md` is closed against v1.6.

### Known limitations after v1.6

- **TUI tests are still manual-only.** Hermetic Textual `Pilot` smoke tests are v1.9 item 4. v1.6 items 4 and 7 (the two TUI changes) were validated by render-preview script + pytest + James' live inspection, not by automated harness.
- **Bulk-apply confirm has no `--auto-apply-high` equivalent for "all" interactive choices.** A user who routinely picks "all" on large batches has to confirm each time once they cross the threshold. By design — the gate's whole purpose is preventing accidental large writes; if they want unattended apply, `--auto-apply-high` is the right tool. Revisit only if friction surfaces.
- **`Examples:` epilog blank-line spacing is collapsed by Rich/Typer.** Examples render tight (one per line) rather than with blank-line separators between them. Readable; matches most CLIs. A formatting tweak would require switching to a different Typer markup mode or a hand-rendered epilog.

---

## v1.5 — UX Polish

Items 19–22 from ROADMAP.md. Two PRs shipped (#24, #25), one item cut, one item attempted and rejected. Test suite from 415 → 444 hermetic tests.

The v1.5 theme is closing out the four pre-Beyond ROADMAP items with display-only improvements: no behavioral changes, no AI prompt edits, no new commands, no architectural refactors. The cycle existed to create a clean visible surface for the upcoming v1.6 deep re-audit, not to add features. Two items shipped on plan; the other two were dispositioned during the cycle and documented rather than forced through.

### Items shipped

**19. Per-batch structured summary panels** (PR #25)
- The end of every enrichment step previously printed a one-line "Done! X applied, Y marked complete" plus a separate token-telemetry line, with each module choosing its own wording and ordering. Reading three step outputs in a session meant context-switching between three slightly different formats.
- New `calibre_toolkit/summary.py` defines a shared `StepSummary` dataclass (tier counters, skip/outcome counters, step-specific breakdowns in `extras`, optional usage + word count) and a `render_summary_panel()` that renders a Rich Panel in either apply or dry-run framing. Rows that don't apply for a given step (e.g. the "Other outcomes" row when nothing was skipped) hide automatically.
- Wired into six call sites: `lcc-enrich`, `comments-enrich` (with word count), `tags-enrich`, `tags-cleanup`, `enrich-identifiers` (with `by_lookup_method` extras), and `clean-titles`. `tags-review` and `clean-identifiers` are deliberately out of scope — the first is interactive per-book and shaped differently, the second is a fix-up command rather than an enrichment batch.
- One internal refactor folded in: `tags._apply_operations` now returns `(total_affected, by_pattern_group, errors)` instead of printing its own end-of-run lines, so the caller in `run_tags_cleanup` can own the `StepSummary` and keep the end-of-run output consistent with the other modules. Contract is internal to the module.

**20. Progress bars for `lcc-enrich` and `comments-enrich`** (PR #24)
- These two step modules still wrapped their AI batch pass in a single `console.status()` spinner with no ETA. On a 50-book batch the user couldn't tell whether to wait or interrupt — every other batch-pass in the toolkit had already gained a `rich.progress.Progress` block with `MofNCompleteColumn`, `TimeElapsedColumn`, and `TimeRemainingColumn`.
- The `progress_callback` plumbing has been in `ai.py` since the tags-cleanup batching pass (`_run_batches_concurrent`), and `suggest_lcc` / `suggest_comments` already accept it. This PR wires the canonical `identifiers.py` Progress block into the two remaining call sites — no shared helper extracted (charter explicitly said copy the pattern, do not abstract at two call sites).
- ROADMAP item 20 wording correction folded in: the original entry listed the identifier loop and `tags.py` as remaining scope, but those had already picked up progress bars in earlier items. Real remaining scope was just `lcc.py` and `comments.py`.

### Items cut or rejected

**21. Memory streaming / chunked rendering for large batches** — cut
- The ROADMAP entry's stated motivation was that "a 1000-book run can exhaust RAM and slow Rich table rendering" in `identifier_enrichment` and `lcc_enrichment`. The charter flagged item 21 as a cut candidate from the start, gated on whether real-library batch sizes actually showed the predicted memory pressure.
- After items 19 and 20 shipped and the toolkit was exercised against the maintainer's ~5K-book library, no RAM pressure or Rich rendering slowdown surfaced. The predicted bottleneck never materialised in practice. Item cut from v1.5 with no follow-up scheduled; ROADMAP entry retained so the analysis isn't lost if RAM pressure shows up in a future, larger workload.

**22. TUI pipeline overview panel** — attempted, rejected
- Implemented on `feat/v1.5-tui-overview` (PR #26): a 5-row summary panel above the existing two-panel TUI layout, each row showing step number, name, progress bar, percentage, and a status icon + verbal label. Tests added (444 → 460), suite green, scope matched the charter exactly.
- Rejected on live inspection in the TUI. The new panel duplicated the left-panel `ListView`, which already rendered step number, name, progress bar, and done/total/% for each MQG step in roughly the same vertical space. The overview's only additions — status icons (●/◐/○) and a verbal "done/in-progress/not-started" label — were inferable at a glance from the bar itself. Net effect was lost screen real estate for the actions panel on the right without added signal.
- PR #26 closed without merge. The branch was discarded and the disposition documented in PR #27 (ROADMAP and v1.5 charter). The lesson recorded for additive-UI items at this polish level: the question is "does this carry information the existing surface doesn't," not "can this be added without breaking anything." If a top-of-screen pipeline view is worth revisiting, the higher-leverage shape is a single-line cross-step summary (e.g. `Pipeline: 1✓ 2◐ 3◐ 4○ 5○ · 2,431/4,872 books fully enriched`), not a re-render of what the left panel already shows.

### Known limitations after v1.5

- **No top-level pipeline-status surface yet.** Item 22's rejection leaves the TUI without a single-line cross-step status view. Per-step status is visible in the left-panel `ListView`; whole-pipeline status requires the user's eye to scan the column. Whether this is worth a future, differently-shaped attempt is open.
- **Large-batch memory behaviour unmeasured at extreme scale.** Item 21 was cut on the basis of no observed pressure at ~5K books. If a future user runs against substantially larger libraries (10K+) and Rich table rendering or peak RSS becomes a problem, the ROADMAP entry remains as scoped work to pick up.

---

## v1.4 — Coherence, Calibration & Scope

Items 16–18 from ROADMAP.md. Three PRs (#19, #20, #21), test suite from 359 → 415 hermetic tests.

The v1.4 theme is making the AI pipeline's outputs verifiable end-to-end: cross-step coherence (item 16) stops two AI steps from contradicting each other, the calibration measurement loop (item 17) closes the long-standing feedback gap between confidence-tier definitions and observed accuracy, and tags-cleanup scoping (item 18) lets vocabulary normalisation operate on a batch without leaking into the rest of the library.

### Items shipped

**16. Cross-step context sharing for tags and comments** (PR #19)
- `tags-mqg` and `comments-enrich` previously ran independently — each AI call saw the book's source metadata but nothing about what the *other* step had produced or proposed. The two outputs could disagree (period tag asserts WWII; comments prose summarises the book as Cold War) and the user would only catch it during review.
- Step 02 (`comments-enrich`) now receives a compact excerpt of the book's current tags in its prompt; step 04 (`tags-mqg`) receives a compact excerpt of the comments. Both excerpts are token-capped and only included when non-empty.
- New `calibre_toolkit/coherence.py` provides two narrow checkers:
  - `check_comments_coherence(comments_html, current_tags)` — flags periods named in AI prose that no current tag supports.
  - `check_tags_coherence(proposed_tags, comments_excerpt)` — flags period tags the AI proposed that the existing prose doesn't mention.
  - The map is intentionally small — false positives kill trust faster than false negatives, so subject coherence is left out. Word-boundary HTML-stripped case-insensitive matching, with WWII / World War II aliasing.
- `CommentsSuggestion` and `TagsSuggestion` each gain a `coherence_warnings: list[str]` field, mirroring the `html_warnings` pattern from item 14. The first warning surfaces in the review table (red, with "+N more" overflow), the full list in the per-book review pane. Failed coherence doesn't auto-discard; the user decides.

**17. Confidence calibration measurement loop** (PR #20)
- Confidence-tier definitions in `rules/lcc.md`, `rules/comments.md`, and `rules/tags.md` were aspirational pre-v1.4: a "high" suggestion was *asserted* to be more accurate than "medium," but nothing verified the claim and there was no feedback loop from applied writes back to the tier definitions. The rules could drift out of calibration silently.
- New `calibre-toolkit audit-confidence` command closes the loop. It samples applied AI writes from the persistent audit log (`~/.calibre-toolkit/audit.log`, in place since item 4), prompts the user to rate each as correct / minor / wrong, and computes per-tier strict and lenient precision. Tiers whose strict precision falls below a configurable threshold (default 70%) are flagged for rule review at the end of the session.
- Sampling is stratified random per `(step, confidence-tier)`. Without stratification high-tier dominates volume in any real audit log, which is exactly the bias the audit is trying to measure around.
- Purely observational. No production code path is touched — the command reads the audit log and queries Calibre for the current field value to compare against what the AI wrote. Manual overrides (current ≠ AI value) are surfaced inline as a hint to the rater. Results persist one session per line to `~/.calibre-toolkit/calibration.jsonl`.
- CLI:
  ```
  calibre-toolkit audit-confidence [--sample-size 20] [--step ...]
                                   [--threshold 0.7] [--seed N]
                                   [--audit-log PATH] [--output PATH]
  ```
- Establishes a new `calibre_toolkit/commands/` subpackage as the first occupant. ROADMAP.md "Beyond v1.5" gains a parking-lot entry to migrate the other top-level commands into `commands/` for consistency in a future PR — the architectural debt is tracked rather than left implicit.

**18. Scope `tags-cleanup` to a search query** (PR #21)
- `tags-cleanup` was always library-wide: the scanner read the full tag vocabulary, the AI semantic pass received it, and every operation applied to every book carrying the source tag. Correct when normalising the whole library at once, wrong when processing a 50-book batch where vocabulary changes were only ever motivated by what's in the queue.
- New `--search` flag accepts any Calibre search query (e.g. `"#metadata_queue:true"`, `"tag:Booker"`). When set, the scanner and AI pass still see the full library vocabulary — frequency counts and semantic-synonym judgements are only meaningful library-wide — but the *application* step filters out ops whose source tags don't appear on any in-scope book. A one-line scope header surfaces what was kept vs. skipped.
- New DB helper `CalibreDB.get_tags_for_books(book_ids)` resolves the scope's tag set in a single SQL round-trip regardless of book count.
- Tag-name comparison is case-sensitive by design — Calibre stores tag names case-sensitively and a case-insensitive compare would over-match (e.g. lowercase `fiction` on a scope book would falsely keep an op that targets the canonical `Fiction`). Locked in by a dedicated test.
- TUI: the Tags Cleanup step gains two new buttons alongside the existing library-wide pair — "Scanner only — metadata queue" and "Full cleanup — metadata queue", both passing `--search "#metadata_queue:true"`.
- **Bug fix folded in:** `_apply_operations` referenced an unbound `ai` symbol at the end-of-run usage summary block — a v1.3-era oversight flagged in PR #19's description that would `NameError` any `tags-cleanup` apply path. Fixed by threading `ai: AIClient | None = None` through from `run_tags_cleanup`.

### Known limitations after v1.4

See `ROADMAP.md` for what's planned next:

- **Calibration ground truth requires user effort.** The new `audit-confidence` loop produces real data only after the user grades a sample. The first run on a fresh library is also the most valuable but also the highest-friction; no shortcut around that.
- **Coherence checking is period-only.** Subject coherence (the harder case — the AI proposes "Cold War history" tags while the prose summarises a memoir) is deliberately out of scope for v1.4 because false positives there would burn trust faster than the true positives recover it. Listed in the v1.5+ parking lot.
- **The catalog-hit summary still reads like a template** ("Classified by Open Library under PR - English Literature.") while the AI-fallback path with item 11's description prefetch produces rich prose. Combining the two paths — catalog truth on structural fields, description-grounded prose on the summary — is captured in the v1.5+ parking lot as `catalog-hit + description-summary`.

---

## v1.3 — Catalog Depth & AI Correctness

Items 10–15 from ROADMAP.md. Six PRs (#10, #11, #12, #13–docs, #14, #15, #16), test suite from 193 → 382 hermetic tests.

### Items shipped

**10. Externalize hardcoded prompts + unify confidence taxonomy** (PR #10)
- Every AI step's preamble and output-format block moved out of `ai.py` and into `rules/prompts/*.md`. Prose edits no longer require a code change.
- New `rules/confidence.md` defines the canonical `high` / `medium` / `low` tier semantics; each step's `SECTION CONF` references the shared file while keeping its step-specific evidence calibration.
- Guard test catches any future regression that reintroduces an inline preamble constant.

**11. Pre-fetch book descriptions for step 03** (PR #11)
- New `calibre_toolkit/services/book_description.py` — Google Books primary, Open Library fallback, both gated through the shared retry helper. HTML is stripped, length capped at 1500 chars on a sentence boundary, MARC artifacts rejected via an 80-char floor.
- Step 03 (`lcc-enrich`) pre-fetches a description for every AI-bound book and passes it into the prompt as authoritative source material; `rules/lcc.md` PATH-06 instructs the AI to summarise from it instead of supplementing with training-data memory.
- Google Books support requires an API key (their quota for anonymous requests is now zero); `description.google_books_api_key` in `config.json` or `GOOGLE_BOOKS_API_KEY` env var. Without a key, only Open Library is queried — a one-line `WARNING` notes the degraded mode. Setup walkthrough in `docs/Getting-Started.md` Step 2a.
- Graceful degradation: any miss surfaces as `None` and the AI falls back to its prior training-data behaviour for that row.

**12. ISBN cross-reference for non-US editions** (PR #12)
- Three new lookup paths in `services/lc_catalog.py`:
  - **OL edition cascade** — resolve seed ISBN to an OL work key, fetch sibling ISBNs of the same work (English-first, capped at 3 to keep worst-case cost predictable on a slow-LC day), retry LC ISBN lookup against each. Catches UK ISBNs whose US sibling is in LC.
  - **LC SRU title+author search** — last resort when no ISBN path hits anything. MARCXML 050 datafield parsing via stdlib `xml.etree`.
  - **Open Library direct ISBN** re-enabled (was filtered out before item 11 provided a real description pipeline). Marked medium confidence with `source_authority="open_library"`.
- The unified `lookup_book()` now walks: LCCN → LC ISBN → OL edition cascade → LC SRU title+author → OL ISBN.
- `_CatalogStats` tracks per-source hit counts; the post-lookup diagnostic line surfaces the breakdown so the impact of each path is visible.

**12a. LC Cloudflare investigation (documentation only)** (PR #13)
- Smoke-testing item 12 revealed LC's public APIs are now behind Cloudflare's JavaScript challenge. Python `urllib` cannot solve it, so every LC HTTP request from the toolkit has been failing silently throughout v1.3 — item 8's honest-source-attribution work means we never lied about it (every fallback correctly resolved to `[AI]`), but the LC pipeline is dormant.
- New `docs/LC-Cloudflare-Investigation.md` captures: what was tested, why simple workarounds (UA spoofing, alternate subdomains) fail, the realistic workaround options (`cloudscraper` / `curl_cffi` / bulk MARC / OAI-PMH / OL-only) with pros and cons, a provenance table for every LCC field, and a pro/con discussion on whether the AI-generated call-number field is worth keeping in its current form when LC is unreachable.
- New roadmap item **12a. Restore LC catalog reachability (Cloudflare workaround)** added to ROADMAP.md.

**13. Token usage & cost telemetry** (PR #14)
- New `calibre_toolkit/usage.py` — `TokenUsage` dataclass with cache-hit-rate property, threadsafe `UsageAggregate`, price table keyed by family prefix (Sonnet/Opus/Haiku 4.x + 3.5), `format_summary()` for the end-of-step panel, persistent JSONL log at `~/.calibre-toolkit/usage.jsonl`.
- Every AI call captures `usage.input_tokens` / `usage.output_tokens` / `cache_creation_input_tokens` / `cache_read_input_tokens`. Each step prints a summary at end of run (both apply mode and dry-run):
  ```
  lcc-enrich · Tokens used: 7,700 input + 3,900 output  (cache: 78,991 read / 4,200 write — 86.9% hit rate)  ≈ $0.12  · 2 API call(s)
  ```
- The cache hit-rate metric directly validates the prompt-caching claim in `ai.py:4–7` — successive batches in the same run pay near-zero for the (large) rules file portion of the prompt.
- TUI displays cumulative spend in the left panel; reads from the persistent log on every refresh.

**14. HTML output validation for comments** (PR #15)
- `_format_comments_html` now `html.escape()`s every AI-supplied string before wrapping. A stray `<script>` tag from a misbehaving response now lands as visible text (`&lt;script&gt;…`) rather than executable HTML in Calibre's comments field.
- New `validate_comments_html()` stdlib-based structural validator confirms the assembled output uses only allow-listed tags (`<h3>`, `<p>`, `<strong>`), no attributes, properly balanced. Catches future regressions if escaping is ever removed.
- `CommentsSuggestion.html_warnings` surfaces validator findings inline in the review table and in `_print_full_suggestion`. Failed validation doesn't auto-discard; the user decides.

**15. Unicode & encoding robustness** (PR #16)
- `normalize_text` now strips combining marks **only** when the base character is in the Latin script. Pre-v1.3 it silently demoted Russian Достоевский to Достоевскии (turning a word into a non-word), Ukrainian/Belarusian ў, Greek polytonic accents, and Arabic/Hebrew vowel marks. Behaviour now:
  - Latin diacritics still strip (`café → cafe`, `Müller → Muller`, `Straße → Strasse`) — unchanged.
  - Cyrillic, Greek, Arabic, Hebrew, CJK, emoji: preserved intact.
- `db.apply_identifiers` previously documented that `:` was filtered from values but the code only checked `,`. Keys weren't sanitised at all. New `_sanitize_identifier()` helper rejects empty entries, the reserved `calibre` key, commas and colons in either side, whitespace inside keys, control characters (`Cc`), and invisible-format characters (`Cf` — zero-width joiner, RTL/LTR marks) in values. Keys are lowercased on the way in.

### Pricing data (for token telemetry)

Anthropic public list prices captured as of January 2026:

| Family | Input | Output | Cache read | Cache write |
|---|---|---|---|---|
| Opus 4.x   | $15.00 | $75.00 | $1.50 | $18.75 |
| Sonnet 4.x | $3.00  | $15.00 | $0.30 | $3.75  |
| Haiku 4.x  | $0.80  | $4.00  | $0.08 | $1.00  |

USD per million tokens. Unknown models report token counts but omit the dollar estimate. Keyed by family prefix so a new minor version inherits pricing until a deliberate update.

### Known limitations after v1.3

See `ROADMAP.md` for the planned work that addresses each:

- **LC catalog is currently unreachable from Python** because of Cloudflare bot protection (`docs/LC-Cloudflare-Investigation.md`). Tracked as item 12a. Until resolved, every `lcc-enrich` row resolves to `[AI]` source. Item 8's attribution work means this is visible, not hidden.
- **The `lcc` call-number field is AI-generated** when LC is unreachable. The class letters are usually correct (and they drive the code-derived primary/secondary class fields, which remain reliable), but the specific Cutter and year are educated guesses. Whether to truncate the field to just the supportable portion is captured as an open product question in the investigation doc.
- **Description coverage depends on Google Books / Open Library reaching the book.** For obscure or very-recent ISBNs, both can miss; the AI then falls back to training-data summaries for those rows (with attribution still honest).

---

> **Note on v1.1 and v1.2:** These milestones shipped without per-version CHANGELOG entries. See `git log v1.0.0..main` for the full history; the key v1.1/v1.2 deliverables are summarised in ROADMAP.md (items 1–9) and the v1.0.0 "Known limitations" section below — most of which v1.1/v1.2 already addressed (onboarding wizard, structured logging, test suite + CI, external-call retry discipline, parallel step 02, Pydantic response validation, honest source attribution, model alias layer).

---

## v1.0.0 — Calibre Metadata Toolkit

Complete rewrite from the original PowerShell-based toolkit. The new toolkit is a Python CLI using Typer, Rich, and direct Calibre integration (SQLite reads + calibredb writes).

### Modules implemented

**MQG-01 — Author & Title Cleanup** (`clean-titles`)
- AI-assisted normalization of author names and book titles
- High/medium/low confidence tiers with per-book review
- MQG completion flag support

**MQG-02 — Identifier Enrichment** (`enrich-identifiers`)
- Uses Calibre's `fetch-ebook-metadata` to find ISBNs, Goodreads IDs, Amazon IDs
- Configurable sufficiency rules and MQG completion requirements
- Manual curation flag for books that cannot be auto-resolved
- `unflag-manual` command to re-queue manually fixed books
- `clean-identifiers` utility for malformed identifier cleanup

**MQG-04 — Comments Enrichment** (`comments-enrich`)
- AI generates a structured 6-section HTML comment per book: The Book, Why It Matters, Award Context, Something You Might Not Know (conditional), Why Read It, Source Notes
- Tone governed by `rules/reader_profile.md` — witty/opinionated (Hitchens/O'Rourke register), moderate right-of-center framing, no identity-first openings
- `--tone-test` flag: generates 3 voice variants (witty-opinionated, neutral-professional, warm-accessible) for one book side-by-side; no writes
- `--dry-run`, `--force`, `--limit` flags matching LCC workflow
- `--ai-provider` / `--ai-model` overrides with same provider-key routing as LCC
- Reads tags, series, publisher, pubdate, existing comments from Calibre for AI context
- Optionally reads `#lcc_summary` as additional subject context
- Confidence tiers: high / medium / low with same tier-based review flow
- `#mqg_comments` completion flag; `#mqg_comments_manual` for flagged books

**MQG-03 — LCC Enrichment** (`lcc-enrich`)
- AI proposes LCC call number, primary class, secondary class, and subject summary
- Primary and secondary class derived from the call number and validated against canonical CSVs
- Confidence tiers: high (catalog-confirmed) / medium (WorldCat consensus) / low (schedule-derived)
- `--dry-run` flag for auditing previously-populated books without writing
- `--force` flag to re-process fully-populated books
- `--limit` flag for test runs
- `--ai-provider` / `--ai-model` flags for per-run provider override (A/B testing)
- K law subclass ranges corrected (KG-KH = Latin America, KJ-KKZ = Europe)
- Canonical drop-down values standardized: `&` throughout, no slashes, no commas
- `#lcc_summary` field: one-sentence subject summary replacing the old hierarchical breadcrumb

**MQG-05 — Tags Enrichment & Cleanup** (`tags-enrich`, `tags-cleanup`, `tags-review`)
- `tags-enrich`: AI proposes 4–8 flat tags per book across four categories — Form (controlled list), Subject, Period, Geography
- LCC fields used as additional context when present; existing tags respected
- Programmatic validation enforces the prompt rules: 4-word cap (silently truncated), no commas (split on first), exactly one Form tag per book (confidence downgraded to medium with diagnostic in notes if violated)
- Confidence tiers (high / medium / low) with the same tier-based review flow as LCC and comments
- `#mqg_tags` completion flag; `#mqg_tags_manual` for flagged books
- `tags-cleanup`: library-wide vocabulary normalisation in two passes
  - Deterministic scanner handles obvious patterns (LCSH date+name drops, bare date ranges, Calibre taxonomy noise, date-range → period-name lookups, formatting); no AI call
  - AI semantic pass handles fuzzy variant matches and near-synonyms the scanner cannot catch; runs only on tags the scanner did not resolve; reason length capped at 10 words
  - Operations grouped by pattern with bulk-approval per group; safe groups default to "apply all", everything else defaults to "review"
  - `--skip-ai` for scanner-only runs; `--min-books` to ignore long-tail tags during the AI pass; `--dry-run` for auditing
- `tags-review`: per-book interactive review of current vs. proposed tags with approve / keep / edit / skip flow; sets `#tags_reviewed` per locked book

**Fixes and improvements (tags pipeline)**

- **`tags-cleanup` batching** — the AI semantic pass previously issued a single API call with the entire tag vocabulary. On libraries with 3000+ tags this exceeded the API timeout. Tags are now sorted alphabetically and batched in chunks of 150, with up to 5 batches running concurrently via the shared `_run_batches_concurrent()` infrastructure. A Rich progress bar shows batch count, elapsed time, and any failed batches. Alphabetical sorting clusters near-variants (e.g. "Sci-Fi" / "Science Fiction") into the same batch.
- **`tags-cleanup` full-table display and `except` approval** — the preview table previously capped at 8 rows. All proposed operations are now shown in full with a leading `#` index column. The apply prompt accepts a new `except` option: enter the row numbers to skip (e.g. `7 12 15`) and everything else is applied in one operation — avoiding hundreds of individual y/n prompts when only a handful of operations need to be declined.
- **`tags-review` validation fix** — Form-tag uniqueness check and 4-word cap were only enforced on the batch `tags-enrich` path. The per-book TUI `tags-review` path bypassed `_validate_proposed_tags()` entirely. Fixed by wiring validation into `_parse_tags_review_response()`.
- **Step 05 TUI surfacing** — the TUI Step 05 panel only exposed three Review actions; `tags-enrich` had no TUI entry point. Added three Enrich actions matching the MQG-04 pattern: "Enrich next N", "Enrich all unprocessed", "Enrich metadata queue".

### Tooling and TUI
- `menu` command launches a Rich-based TUI covering all pipeline steps and maintenance commands

### Infrastructure
- `library-info` command for diagnosing library/calibredb scope discrepancies
- Per-command AI config override (`ai.lcc`, `ai.comments`, `ai.tags` blocks in config.json)
- Provider-aware API key routing (supports OpenAI and Anthropic keys simultaneously)
- Canonical CSV validation for all enumeration fields
- LC catalog lookup via LCCN and ISBN with parallel HTTP requests; Open Library fallback currently disabled pending the summary-quality and source-attribution work tracked in ROADMAP

### Known limitations (see ROADMAP.md)
- `#lcc_summary` is AI-drafted from training memory; treat as provisional. The book-description pre-fetch work will replace this with publisher-sourced content
- Source attribution in AI-only LCC suggestions may name "Library of Congress catalog" even when no catalog record was consulted; classifications themselves are independently usable
- UK and other non-US ISBNs typically miss the LC catalog and fall through to AI
- Step 02 identifier lookups are sequential and slow on large batches
