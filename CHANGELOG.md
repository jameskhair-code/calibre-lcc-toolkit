# Changelog

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
