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

### Infrastructure
- `library-info` command for diagnosing library/calibredb scope discrepancies
- Per-command AI config override (`ai.lcc` block in config.json)
- Provider-aware API key routing (supports OpenAI and Anthropic keys simultaneously)
- Canonical CSV validation for all enumeration fields
