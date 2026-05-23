# Changelog

---

## Current — Python CLI Rebuild

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
