# Roadmap

22 items in dependency order, targeting v1.5. Each item is a separate PR. When
implementation begins, a GitHub Issue is created from the item's prose with the
corresponding milestone attached.

## Milestones

| Milestone | Items | Theme |
|-----------|-------|-------|
| **v1.1** | 1–4 | Foundation: onboarding, CLI cleanup, tests, logging |
| **v1.2** | 5–9 | Reliability: external calls, parallelization, schema validation, attribution, model aliases |
| **v1.3** | 10–15 | Catalog depth & AI correctness: prompt architecture, pre-fetch, ISBN cross-reference, telemetry, HTML safety, unicode |
| **v1.4** | 16–18 | AI coherence: cross-step context, calibration, scoped tags |
| **v1.5** | 19–22 | UX polish: summary reports, progress bars, streaming, TUI overview |

---

## v1.1 — Foundation

### 1. Library health-check + onboarding (`doctor` / `init` / `setup-columns`)

**Problem.** A new user faces a 30-minute manual setup: hand-edit JSON, create 14
custom Calibre columns via the GUI (including loading 21+231 enumeration values from
CSVs by hand), and only discover mistakes mid-batch. No upfront validation exists.

**Approach.** Three commands:
- `doctor` — one-pass validation: `config.json` parses and has required keys,
  `library_path` has `metadata.db`, `calibredb --version` works, API key
  authenticates, all 14 custom columns exist with correct types. Actionable error
  report.
- `init` — interactive wizard: prompts for library path (verified), calibredb path
  (tested), API key (tested with a minimal call), per-step model choices. Writes
  `config.json` atomically.
- `setup-columns` — creates the 14 required custom columns via
  `calibredb add_custom_column`, loads enumeration values from
  `config/lcc-*-canonical.csv`. Idempotent.

**Touch points.** New commands in `cli.py`; `db.py` (column type validation);
`config.example.json`.

**Risk.** Low. Commands are read-heavy; `setup-columns` writes only when columns
are absent.

**Expected impact.** Reduces new-setup time from 30 minutes to under 5; catches
95% of config mistakes before any batch runs.

---

### 2. CLI flag consistency + tier-default documentation

**Problem.** Flag names differ across commands: `--auto-apply-high` (lcc,
identifiers) vs `--auto-approve` (tags-review); `--force` vs `--force-lookup`;
`--dry-run` help text varies. Tier defaults (high → "all", medium → "review",
low → "skip") are undocumented — new users type the same defaults manually every
time.

**Approach.** Standardize flag names with deprecation aliases for old names;
document tier defaults inline in `--help` and in Getting-Started. No behaviour
changes.

**Touch points.** `cli.py` (flag names, help strings); `docs/Getting-Started.md`.

**Risk.** Low. Purely text changes plus deprecation aliases.

**Expected impact.** Reduces cognitive load; tier defaults become discoverable.

---

### 3. Test suite + CI

**Problem.** Zero automated tests. There is no safety net for any of the items
below.

**Approach.** Start with the highest-value unit targets: parsers
(`_extract_json_array`/`_extract_json_object` in `ai.py:41–60`), validators
(`_validate_proposed_tags` in `ai.py:1048–1070`), the tag scanner rule set
(`tag_scanner.py`), and LC catalog response parsers. Use fixture-recorded JSON
responses so tests are hermetic — no live API calls. Add a GitHub Actions workflow
on push/PR.

**Touch points.** New `tests/` directory, `conftest.py`, `pytest.ini`,
`.github/workflows/ci.yml`.

**Risk.** Low. Purely additive.

**Expected impact.** Foundation for every subsequent item; regressions caught
automatically.

---

### 4. Structured logging + persistent audit log

**Problem.** No logging infrastructure exists. `db.py:239` uses bare `print` for
warnings. When a batch fails or produces unexpected results, there is no way to
diagnose why post-hoc. AI prompts and responses are never persisted.

**Approach.** Adopt stdlib `logging` throughout the codebase. Add `--verbose` and
`--log-file` flags to all commands (default silent). At DEBUG level, log truncated
prompts and responses. All metadata writes appended to
`~/.calibre-toolkit/audit.log` (JSONL):
`{timestamp, book_id, field, new_value, confidence, source}` — a factual change
history.

**Touch points.** New `calibre_toolkit/logging_config.py`; all modules; `cli.py`.

**Risk.** Low. Purely additive; defaults to silent.

**Expected impact.** Enables post-batch diagnosis; provides a permanent "what did
this session change?" trail.

---

## v1.2 — Reliability

### 5. External-call discipline (timeouts, retries, graceful degradation)

**Problem.** Three external surfaces have inconsistent behaviour:
- Anthropic client (`ai.py:385`): 120s timeout hard-coded, no config knob.
- `fetch-ebook-metadata` subprocess (`fetcher.py:82`): per-call timeout exists but
  binary health is not probed; failures surface poorly.
- LC catalog (`lc_catalog.py:49–62`): returns `None` on any failure with no retry
  — a 1–2s outage silently drops a row to AI classification.

**Approach.** Unify under a shared retry/backoff helper (exponential, 3 retries).
Expose `request_timeout_seconds` and `max_retries` per service in `config.json`
under `anthropic`, `fetcher`, and `catalog` keys. Log at DEBUG level on each retry.
Probe the fetcher binary at startup.

**Touch points.** `ai.py`; `fetcher.py`; `lc_catalog.py`; `config.example.json`.

**Risk.** Low. Existing happy paths unchanged; only failure handling improves.

**Expected impact.** Brief catalog outages no longer silently degrade to AI-only;
Anthropic timeouts are user-configurable.

---

### 6. Parallelize step 02 (identifier lookups)

**Problem.** Step 02 calls `fetch-ebook-metadata` once per book in a sequential
loop (`identifiers.py:277`). Each call can take 5–15s. A 50-book batch takes
5–10 minutes of wall time.

**Approach.** Wrap the lookup loop in a `ThreadPoolExecutor` with 3–5 workers
(configurable). `subprocess.run()` releases the GIL, so threading gives real
concurrency for I/O-bound work. Collect results after all lookups complete — same
review table as now. Use a Rich progress bar instead of per-book `console.status()`
to avoid interleaved output.

**Touch points.** `calibre_toolkit/modules/identifiers.py`;
`calibre_toolkit/fetcher.py`. Add `max_workers` to `config.json` identifiers
section.

**Risk.** Low. Lookups are independent; no shared state. Main concern is Rich
console interleaving — solved by the progress bar.

**Expected impact.** 50-book batch from ~5–10 min to ~1–2 min.

---

### 7. Strict response schema validation with retry-on-violation

**Problem.** `_extract_json_*` (`ai.py:41–60`) parses AI responses but doesn't
validate shape. Most schema violations propagate silently or fail late — e.g., the
Form-tag count check (`ai.py:1048`) downgrades confidence after the fact rather
than correcting at generation time.

**Approach.** Add Pydantic models per response type. On shape violation, retry once
with a targeted correction prompt. On second failure, fail the row cleanly with a
visible error. Validate before iterating, not mid-loop.

**Touch points.** `ai.py` (all `_parse_*` functions and suggestion dataclasses);
`modules/*.py` (surface validation errors at review time).

**Risk.** Low. Purely additive validation; happy path unchanged.

**Expected impact.** Silent data corruption eliminated; retries correct the majority
of one-off AI formatting mistakes.

---

### 8. Honest source attribution (`[AI]` / `[LC]` / `[OL]`)

**Problem.** When step 03 falls through to AI classification, the AI frequently
writes Source notes like *"Library of Congress catalog, exact ISBN match"* even
though no LC record was consulted. The diagnostic header correctly reports
`0 catalog hits`, but per-row source text overstates confidence. A future audit
cannot distinguish AI-only from catalog-confirmed classifications.

**Approach — two layers:**

1. **Structural separation in the prompt.** Restructure `rules/lcc.md` so the AI
   is given an explicit `source_authority` enum: `lc_catalog` |
   `worldcat_consensus` | `ai_inference`. Enforce in `_parse_lcc_response()`: if no
   `CatalogHit` was passed in, reject `lc_catalog` or `worldcat_consensus` and
   downgrade to `ai_inference`.

2. **Display-layer override.** In `_build_suggestion_table()` (`lcc.py`), prepend a
   deterministic provenance prefix — `[AI]`, `[LC]`, `[OL]` — based on actual hit
   type. The AI's free-text reasoning follows.

**Touch points.** `rules/lcc.md`; `calibre_toolkit/ai.py` (`_parse_lcc_response`,
validation); `calibre_toolkit/modules/lcc.py` (`_build_suggestion_table`).

**Risk.** Low. Backward-compatible — `#lcc_*` columns unaffected; change is display
and validation only.

**Expected impact.** A future audit can trust the source field. Reviewers in step 03
immediately see which rows are AI-only.

---

### 9. Model alias layer for forward-compatible migration

**Problem.** `claude-sonnet-4-6` is hardcoded in `ai.py:375` and
`config.example.json`. When a new model ships, every user must hand-edit.

**Approach.** Add `calibre_toolkit/models.py` with named aliases (`fast`, `latest`,
`legacy`) and a deprecation table. Accept aliases in `config.json` and via
`--ai-model` flag. Document migration policy.

**Touch points.** New `calibre_toolkit/models.py`; `ai.py`; `cli.py`;
`config.example.json`.

**Risk.** Low. Aliases resolve to the same model IDs as before; no behaviour
change.

**Expected impact.** Model migrations become a one-line change in `models.py`.

---

## v1.3 — Catalog Depth & AI Correctness

### 10. Externalize hardcoded prompts + unify confidence taxonomy

**Problem.** `ai.py:234–267, 600–634, 698–741, 837–861, 936–971` embeds prose
preambles and output-format blocks in Python. When a `rules/*.md` file changes,
the inline preamble doesn't auto-sync — silent drift. Confidence tier definitions
also differ across `rules/lcc.md` (CONF-01-05), `rules/comments.md` (CONF-01-03),
and `rules/tags.md` (CONF-01-04) with no shared reference.

**Approach.** Move all preambles and output-format blocks into `rules/*.md` (or a
new `rules/prompts/` directory), loaded at runtime. Create `rules/confidence.md` as
the single source of confidence-tier definitions, referenced from each step's prompt
file.

**Touch points.** `ai.py` (all `_build_*_system_message` functions); all
`rules/*.md`; new `rules/confidence.md`.

**Risk.** Moderate. Prompt content changes require re-testing. Do one step at a
time.

**Expected impact.** Single source of truth for prompt content; rules edits flow
through without code changes.

---

### 11. Pre-fetch book descriptions for step 03 (eliminate `lcc_summary` hallucination)

**Problem.** Step 03 sends only title, authors, and ISBN to the AI. For obscure
books, the AI generates `lcc_summary` from training memory and can hallucinate plot
details.

**Approach.** Before the AI call, fetch the publisher description and subject
categories from Google Books API (`GET volumes?q=isbn:<isbn>`, no key required for
basic lookups). Fall back to Open Library by ISBN. Pass the fetched description into
the AI prompt as authoritative source material. Update `rules/lcc.md`: "When a
description is provided, summarize from it; do not supplement from training data."

**Touch points.** New `calibre_toolkit/services/book_description.py`;
`_build_lcc_user_message()` in `ai.py`; `rules/lcc.md` PATH section.

**Risk.** Moderate. Adds a network dependency to step 03 (graceful degradation
required). Prompt structure changes need re-testing.

**Expected impact.** Hallucination becomes structurally impossible for any book
Google Books or OL has indexed.

---

### 12. ISBN cross-reference for non-US editions (improve catalog hit rate)

**Problem.** UK and non-US ISBNs rarely match LC catalog records directly. A
50-book batch of UK-published literary fiction yielded 0 direct LC catalog hits.
Open Library was disabled in v1.0 because it lacks reliable summaries — now
solvable via item 11.

**Approach — two complementary strategies:**

1. **Open Library edition cascade.** OL's `/api/books?bibkeys=ISBN:…&jscmd=details`
   response includes `works[0].key`. Fetching `{work_key}/editions.json` returns all
   known editions with their ISBNs. Re-run `lookup_by_isbn()` against each US ISBN
   found there. Re-enable OL once item 11 provides a real summary pipeline.

2. **LC SRU title+author search.** When ISBN lookups fail, query LC's SRU endpoint
   with title and author. Returns MARCXML; parse `<marc:datafield tag="050">` for
   the LC call number.

**Touch points.** `calibre_toolkit/services/lc_catalog.py` — add
`lookup_by_isbn_with_edition_cascade()` and `lookup_by_title_author_sru()`. Update
`lookup_book()` to try these after direct ISBN miss. Re-enable OL ISBN lookup
(currently filtered at `lcc.py:310`).

**Risk.** Moderate. Edition cascade adds 1–2 HTTP calls per miss; SRU response is
XML-heavy. Both gated behind existing catalog call timeout.

**Expected impact.** For UK/international-heavy collections, catalog hit rate from
near-0% to 40–60%.

---

### 12a. Restore LC catalog reachability (Cloudflare workaround)

**Problem.** Discovered during item 12 smoke testing: every LC public API
(`www.loc.gov`, `lx2.loc.gov`) is now behind Cloudflare's JavaScript challenge.
Python's `urllib` cannot solve the challenge, so every LC HTTP request from
this tool fails — silently, with timeouts or HTML challenge pages. Realistic
User-Agent spoofing was tested and is insufficient (Cloudflare fingerprints
the TLS handshake and request behaviour, not just the UA string). This has
been the case throughout v1.3 development, not just on the day of discovery —
item 8's honest-source-attribution work was already correctly resolving every
fallback to `[AI]`, so the user is not being misled, but the v1.1 / v1.2 /
v1.3 LC pipeline is dormant until a workaround ships.

**Approach.** Investigate and decide between these options (full pros/cons in
`docs/LC-Cloudflare-Investigation.md`):

- **`cloudscraper`** — pure-Python JS-challenge solver. Drop-in, small dep,
  but Cloudflare evolves and may break it.
- **`curl_cffi`** — libcurl wrapper with browser TLS fingerprint
  impersonation. Heavier dep, more robust against fingerprint detection.
- **LC bulk MARC datasets** — monthly snapshots, local index. No live
  service dependency but ~10GB+ of data and a separate offline-mode code
  path.
- **LC OAI-PMH endpoint** — historically whitelisted for harvesters; may
  bypass Cloudflare. XML-heavy and not designed for single-record lookups.
- **Drop LC entirely** — lean on Open Library for everything. Loses access
  to LC's deeper catalog for non-US books.

Pick one approach (probably `curl_cffi` for robustness or OAI-PMH for
politeness), implement in `services/lc_catalog.py`, verify against a real
batch, document the new dependency / approach in `docs/Getting-Started.md`.

**Touch points.** `calibre_toolkit/services/lc_catalog.py`; possibly
`pyproject.toml` (new dependency); `docs/Getting-Started.md`;
`docs/LC-Cloudflare-Investigation.md` (mark resolved when shipped).

**Risk.** Moderate–high. All approaches are fragile against Cloudflare
updates (option 1, 2) or operationally heavy (option 3). The OL fallback
shipped in item 12 cushions this — the toolkit still works without LC,
just with lower hit rate on non-US books.

**Expected impact.** Restores the dormant cascade work from items 5, 8, 12.
Restores the call-number field's value as a catalog-verified field rather
than an AI-generated guess. Should also prompt a separate question (also
captured in the investigation doc): is the AI-generated call-number field
worth keeping in its current form when LC is unreachable, or should it be
truncated to its supportable portion (class letters only)?

---

### 13. Token usage & cost telemetry

**Problem.** No token tracking exists. After running an AI step, users have no idea
how many tokens were consumed or the approximate cost.

**Approach.** Capture `usage.input_tokens` / `usage.output_tokens` from every
Anthropic response in `ai.py`. Sum per-batch and per-run. At end of each step,
report: `Tokens used: 45,230 input + 12,104 output ≈ $0.47`. Cumulative totals
visible in the TUI overview panel. Also validate prompt-cache hit rate against the
claim in `ai.py:4–7`.

**Touch points.** `ai.py` (AIClient); all step modules (end-of-run display);
`tui/app.py` (stats panel).

**Risk.** Low. Read-only from Anthropic response; no behaviour change.

**Expected impact.** Users can track spend per batch and per step; caching
effectiveness is measurable.

---

### 14. HTML output validation for comments

**Problem.** `_format_comments_html` (`ai.py:772–788`) wraps AI text in `<h3>`/`<p>`
tags without escaping the content. A stray `<` or `<script>` tag in AI output
produces malformed HTML written directly to Calibre's comment field.

**Approach.** Escape AI-returned text before insertion using `html.escape()`. Run a
lightweight validator (e.g., `html5lib`) on the assembled output. Surface a visible
warning during step 04 review if validation fails; do not write malformed HTML.

**Touch points.** `ai.py:772–788`; `calibre_toolkit/modules/comments.py`.

**Risk.** Low. Additive validation; well-formed AI output passes unchanged.

**Expected impact.** Prevents malformed comment fields; removes a latent injection
surface.

---

### 15. Unicode & encoding robustness

**Problem.** No test coverage exists for CJK titles, accented authors, or emoji.
`normalize_text` (in `normalize.py`) may silently strip diacritics. Identifier
sanitization (`db.py:575–578`) only checks for `,`.

**Approach.** Add fixture tests with non-Latin metadata (CJK, Arabic, accented
Latin, emoji). Verify `normalize_text` preserves or intentionally strips data —
document the decision. Tighten identifier sanitization at the calibredb boundary.

**Touch points.** `calibre_toolkit/normalize.py`; `calibre_toolkit/db.py`; test
fixtures.

**Risk.** Moderate if bugs found (silent data loss). Low risk for the changes
themselves.

**Expected impact.** Confidence that non-Latin metadata moves through the pipeline
without silent loss.

---

## v1.4 — AI Coherence

### 16. Cross-step context sharing

**Problem.** Step 04 (comments) reads `#lcc_summary` but not current tags. Step 05
(tags) reads LCC fields but not comments. The two steps can produce contradictions
— a comment discussing the Cold War while tags have no period tag.

**Approach.** Pass current tags into the comments AI prompt as a secondary context
signal. Pass a comments excerpt into the tags AI prompt. Add an optional post-batch
consistency check that flags obvious cross-step mismatches and surfaces them at the
end of the step's review.

**Touch points.** `ai.py` (`suggest_comments`, `suggest_tags`);
`calibre_toolkit/modules/comments.py`; `calibre_toolkit/modules/tags.py`.

**Risk.** Moderate. Prompt structure changes require re-testing.

**Expected impact.** Coherence across steps; reduces contradictions in the final
metadata.

---

### 17. Confidence calibration measurement loop

**Problem.** No way to verify whether high-confidence AI suggestions are actually
more accurate than medium. No feedback loop exists.

**Approach.** Add an `audit-confidence` command that samples N applied books per
step (configurable, default 20), prompts the user to rate each suggestion as
correct / minor / wrong, computes precision per confidence tier, and flags tiers
where precision falls below a configurable threshold. Results logged to a
calibration file.

**Touch points.** New `calibre_toolkit/commands/audit.py`; `cli.py`; all
`rules/*.md` confidence sections.

**Risk.** Low. No production code changes; purely additive.

**Expected impact.** Confidence tier definitions become data-driven rather than
aspirational.

---

### 18. Scope tags-cleanup to metadata queue

**Problem.** `tags-cleanup` always operates library-wide. Users processing a 50-book
batch cannot scope vocabulary normalisation to just those books without running the
full library pass.

**Approach (Option A — filter candidates, retain global stats).** The scanner and AI
semantic pass continue to receive the full library tag vocabulary (frequency counts
are only meaningful library-wide). The change is in the *application* step: before
writing, check whether affected books intersect the requested search scope.
Operations that touch no in-scope books are silently skipped.

1. Add an optional `search_query: str | None` parameter to `run_tags_cleanup()` in
   `calibre_toolkit/modules/tags.py`.
2. When set, load the book IDs matching the query and map tags to those books.
3. In the operation-application loop, skip ops where no affected book is in scope.
4. Add a `--search` argument to the `tags-cleanup` CLI command.
5. Add two TUI buttons: "Scanner only — metadata queue" and "Full cleanup — metadata
   queue", passing `--search "#metadata_queue:true"`.

**Touch points.** `calibre_toolkit/modules/tags.py` (`run_tags_cleanup`);
`calibre_toolkit/cli.py`; `calibre_toolkit/tui/app.py`.

**Risk.** Low. Library-wide path unchanged; scope filter is additive.

---

## v1.5 — UX Polish

### 19. Per-batch summary reports

**Problem.** After a step, the user sees a one-line total (`lcc.py:710–716` is
typical). No breakdown: tier distribution, skip reasons, method-level success for
identifiers, per-category tag counts, cost.

**Approach.** Replace the one-liner with a structured summary panel at end of each
step run: high/med/low count applied per tier; skip reasons (already done,
validation failed, declined); per-method success for identifiers; per-category
counts for tags; word count + cost (from item 13); elapsed time; session timestamp.

**Touch points.** All step modules (end-of-run display); `cli.py`.

**Risk.** Low. Display-only.

**Expected impact.** Users can audit their work, plan the next batch, and track
progress over time.

---

### 20. Progress bars with ETA across long-running operations

**Problem.** Identifier lookups and tags-cleanup AI batches show only
`[5/50] Looking up…` with no ETA. On a 50-book batch users don't know whether to
wait or interrupt.

**Approach.** Switch to `rich.progress.Progress` with `TimeElapsed`,
`TimeRemaining`, and `MofNComplete` columns. The pattern already exists in the
tags-cleanup AI batching pass (`_run_batches_concurrent`); port it to the identifier
loop, lcc-enrich batch, and comments-enrich batch.

**Touch points.** `calibre_toolkit/modules/identifiers.py`;
`calibre_toolkit/modules/tags.py`; `calibre_toolkit/modules/lcc.py`.

**Risk.** Low. Display-only.

---

### 21. Memory streaming / chunked rendering for large batches

**Problem.** `identifier_enrichment` (`identifiers.py:275–323`) and
`lcc_enrichment` (`lcc.py:602`) collect all results before display. A 1000-book
run can exhaust RAM and slow Rich table rendering.

**Approach.** Switch to chunked display (show results in groups of 20–50) and
generators in the apply loop.

**Touch points.** All enrichment modules with large result tables; Rich table
rendering helpers.

**Risk.** Low. Optimization only; results are identical.

---

### 22. TUI pipeline overview panel

**Problem.** The TUI shows per-step stats in a vertical list but no top-level "where
am I in the pipeline" view. Users can't quickly assess which steps are complete and
which remain.

**Approach.** Add a 5-row summary panel at the top of the TUI menu (above the
current two-panel layout) showing each step's progress bar, percentage, and a
done ✓ / in-progress → / not-started indicator. Refresh on `r`; tap to jump to
that step. Data already loaded in `tui/app.py:456–510`.

**Touch points.** `calibre_toolkit/tui/app.py` (stats loading, layout).

**Risk.** Low. Additive UI panel.

**Expected impact.** At-a-glance pipeline status; useful at the start of every
session.

---

## Process notes

- Each item is a single focused PR off `main`.
- When implementation begins, open a GitHub Issue from the item's prose with the
  corresponding milestone (v1.1–v1.5) attached.
- Move items to CHANGELOG.md when shipped.
- Add new items by appending; preserve sequencing rationale.
