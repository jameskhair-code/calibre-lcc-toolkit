# Roadmap

Post-v1.0 enhancements. Order is by priority, not commitment.

---

## Parallelize step 02 (identifier lookups)

**Problem.** Step 02 calls Calibre's `fetch-ebook-metadata` once per book in a
sequential `for` loop (`identifiers.py:277`). Each call spawns a subprocess that
queries multiple metadata sources serially and can take 5–15s. A 50-book batch
is ~5–10 minutes of wall time.

**Approach.** Wrap the lookup loop in a `ThreadPoolExecutor` with 3–5 workers.
`subprocess.run()` releases the GIL, so threading gives real concurrency for
this I/O-bound work. The review table is collected after all lookups complete,
same as now — no UX change beyond a progress callback.

**Touch points.** `calibre_toolkit/modules/identifiers.py`,
`calibre_toolkit/fetcher.py`. Possibly add a `max_workers` config in the
identifiers section of `config.json`.

**Risk.** Low. The lookups are independent; no shared state to protect. Main
concern is rich console output interleaving — should buffer per-book status
lines or use a progress bar instead of `console.status()` per book.

**Expected impact.** 50-book batch from ~5 min to ~1–2 min.

---

## Pre-fetch book descriptions for step 03 (eliminate lcc_summary hallucination)

**Problem.** Step 03 sends the AI only title, authors, and ISBN. For obscure
books, the AI generates `lcc_summary` from training memory and can hallucinate
plot details. Visible to users as "low confidence" rows where the summary
sounds plausible but may be partly wrong.

**Approach.** Before the AI call, fetch the publisher description and subject
categories from Google Books API (`GET volumes?q=isbn:<isbn>`, no API key
required for basic lookups). Fall back to Open Library by ISBN. Pass the
fetched description into the AI prompt as authoritative source material.
Update `rules/lcc.md` to instruct: "When a description is provided, summarize
from it; do not supplement from training data."

**Touch points.** New `calibre_toolkit/services/book_description.py`. Update
`_build_lcc_user_message()` in `ai.py` to include the description when present.
Update `rules/lcc.md` PATH section.

**Risk.** Moderate. Adds a network dependency to step 03 (need graceful
degradation when APIs are unreachable). Prompt structure changes will need
re-testing on a representative batch.

**Expected impact.** Hallucination becomes structurally impossible for any
book Google Books or Open Library has indexed. For genuinely unindexed books,
the AI gets an explicit "no description found" signal and can mark low
confidence honestly instead of guessing.

---

## ISBN cross-reference for non-US editions (improve catalog hit rate)

**Problem.** UK and other non-US ISBNs rarely match LC catalog records directly.
LC catalogues under the US publisher's ISBN. A 50-book batch of literary fiction
(heavily UK-published) yielded 0 direct LC catalog hits; Open Library picked up
16 but was disabled (v1.0) because it lacks reliable summaries. The batch fell
entirely to AI classification.

**Approach — two complementary strategies:**

1. **Open Library edition cascade.** OL's `/api/books?bibkeys=ISBN:{isbn}&jscmd=details`
   response includes `works[0].key`. Fetching `{work_key}/editions.json` returns all
   known editions with their ISBNs. Re-run `lookup_by_isbn()` against each US ISBN
   found among those editions. This crosses the UK→US ISBN bridge using OL as an
   index, then confirms via LC.

2. **LC SRU title+author search.** When ISBN lookups fail, query LC's SRU endpoint
   (`https://lx2.loc.gov/sru/...`) with title and author. Returns MARCXML records;
   parse `<marc:datafield tag="050">` for the LC call number. Works independently
   of ISBN and covers books LC has catalogued under any edition.

**Touch points.** `calibre_toolkit/services/lc_catalog.py` — add
`lookup_by_isbn_with_edition_cascade()` and `lookup_by_title_author_sru()`.
Update `lookup_book()` to try these after direct ISBN miss.
Re-enable Open Library ISBN lookup (currently filtered at `lcc.py:310`) once
a real summary source is wired in via the book-description pre-fetch item above.

**Risk.** Moderate. Edition cascade adds 1–2 extra HTTP calls per miss; SRU
response is XML-heavy. Both should be gated behind the same timeout as existing
catalog calls. Combine with the book-description pre-fetch item so OL re-enablement
lands with a real summary pipeline, not the placeholder.

**Expected impact.** For collections heavy in UK/international editions, catalog
hit rate should rise from near-0 to 40–60% — reducing AI-only classifications
and improving `lcc` field accuracy.

---

## Honest source attribution in AI-generated suggestions

**Problem.** When step 03 falls through to AI classification (no catalog hit),
the AI frequently writes Source notes like *"Library of Congress catalog, exact
ISBN match — LC record confirms this call number for the 1997 edition"* even
though no LC record was consulted. The diagnostic header correctly reports
`0 catalog hits`, but per-row source text overstates confidence. Risk: a
future reader of the metadata (or a future maintainer auditing the library)
cannot distinguish AI-only classifications from catalog-confirmed ones by
reading the source field.

**Approach — two layers:**

1. **Structural separation in the prompt.** Restructure `rules/lcc.md` so the
   AI is given an explicit `source_authority` field with a fixed enum:
   `lc_catalog` | `worldcat_consensus` | `ai_inference`. The free-text
   `source` field then describes *reasoning*, not provenance. Enforce in
   `_parse_lcc_response()`: if no `CatalogHit` was passed in, reject any
   `lc_catalog` or `worldcat_consensus` value and downgrade to `ai_inference`.

2. **Display-layer override.** In `_build_suggestion_table()` (lcc.py), prepend
   a deterministic provenance prefix to the source column based on whether a
   catalog hit existed: `[AI]`, `[LC]`, `[OL]`. The AI's free-text reasoning
   follows. This makes the distinction impossible to fake at render time.

**Touch points.** `rules/lcc.md` (PROMPT/SOURCE section), `calibre_toolkit/ai.py`
(`_parse_lcc_response`, validation), `calibre_toolkit/modules/lcc.py`
(`_build_suggestion_table` row rendering).

**Risk.** Low. Backward-compatible — existing `#lcc_*` columns unaffected; the
change is purely in how suggestions are *displayed and validated* before
write. No library migration needed.

**Expected impact.** A future audit of the library can trust the source field.
Reviewers in step 03 can immediately see which rows are AI-only and apply
appropriate skepticism, rather than being misled by fabricated catalog
citations.

---

## Process notes

- Each item above is a single focused PR off `main`, not bundled work.
- Add new items by appending; keep ordering loose.
- Move items to CHANGELOG.md when shipped.
