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

## Process notes

- Each item above is a single focused PR off `main`, not bundled work.
- Add new items by appending; keep ordering loose.
- Move items to CHANGELOG.md when shipped.
