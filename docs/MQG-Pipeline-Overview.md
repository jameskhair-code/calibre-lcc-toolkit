# MQG Pipeline — v1.0 Reference

Authoritative reference for the five-step Calibre metadata enrichment pipeline.
For setup instructions see [Getting-Started.md](Getting-Started.md).
For post-v1.0 planned work see [ROADMAP.md](../ROADMAP.md).

---

## What It Does

The toolkit enriches Calibre library metadata through five sequential steps ("MQG").
Each step is human-in-the-loop: the AI proposes, a review table shows confidence
tiers, and you approve before anything is written to Calibre.

| Step | Command | What it populates |
|------|---------|------------------|
| MQG-01 | `clean-titles` | Normalized author names and book titles |
| MQG-02 | `enrich-identifiers` | ISBNs, Goodreads IDs, Amazon IDs |
| MQG-03 | `lcc-enrich` | LCC call number, primary class, secondary class, subject summary |
| MQG-04 | `comments-enrich` | Structured 6-section HTML book description |
| MQG-05 | `tags-enrich` | 4–8 flat subject tags (Form, Subject, Period, Geography) |

---

## Entry Points

**Recommended:** Launch the TUI menu for interactive sessions:

```bash
py -m calibre_toolkit.cli menu
```

**Or run any command directly:**

```bash
py -m calibre_toolkit.cli <command> [search-query] [options]
```

All commands accept `--limit N`, `--dry-run`, and `--force`. See `--help` on any
command for full option details.

---

## Pipeline Flow

Books advance through the pipeline via completion flags. Each step sets a `#mqg_*`
Yes/No column when a book is accepted; the next step filters on it.

```
[all books]
    │
    ▼ MQG-01  clean-titles
    │         sets #mqg_title_author
    │
    ▼ MQG-02  enrich-identifiers
    │         sets #mqg_identifiers
    │         (requires ISBN + grrating/grvotes before marking complete)
    │
    ▼ MQG-03  lcc-enrich
    │         sets #mqg_lcc
    │         consults LC catalog by LCCN/ISBN first; falls through to AI
    │
    ▼ MQG-04  comments-enrich
    │         sets #mqg_comments
    │         reads #lcc_summary as additional context when available
    │
    ▼ MQG-05  tags-enrich
              sets #mqg_tags
              reads LCC fields as additional context when available
```

Typical search queries:

```bash
# MQG-01
py -m calibre_toolkit.cli clean-titles "#metadata_queue:true"

# MQG-02
py -m calibre_toolkit.cli enrich-identifiers "#mqg_title_author:true and not #mqg_identifiers:true"

# MQG-03
py -m calibre_toolkit.cli lcc-enrich "#mqg_identifiers:true and not #mqg_lcc:true"

# MQG-04
py -m calibre_toolkit.cli comments-enrich "#mqg_lcc:true and not #mqg_comments:true"

# MQG-05
py -m calibre_toolkit.cli tags-enrich "#mqg_lcc:true and not #mqg_tags:true"
```

---

## Confidence Tiers

All enrichment steps display confidence per book:

| Symbol | Tier | Meaning |
|--------|------|---------|
| ● | High | Strong evidence (catalog hit, LCC class confirmed) |
| ◐ | Medium | Reasonable inference; minor uncertainty |
| ○ | Low | Weak signal; manual review recommended |

Tier 1 / Tier 2 / Tier 3 batch prompts let you approve high-confidence results
in bulk while reviewing or skipping lower-confidence ones.

---

## MQG-05 Tag Tools

Step 05 has three distinct tools:

| Tool | Command | When to use |
|------|---------|-------------|
| `tags-enrich` | `py -m calibre_toolkit.cli tags-enrich` | Add tags to new/untagged books |
| `tags-review` | `py -m calibre_toolkit.cli tags-review` | Per-book interactive review of any book's tags |
| `tags-cleanup` | `py -m calibre_toolkit.cli tags-cleanup` | Library-wide vocabulary normalisation (variants, noise, casing) |

Run `tags-enrich` first to build the tag set. Run `tags-cleanup` periodically
to keep the vocabulary clean. Run `tags-review` for per-book audit or correction.

`tags-cleanup` runs two passes:
1. **Deterministic scanner** — pattern-based rules for LCSH fragments, BISAC codes, encoding noise, date ranges. Fast, no AI cost. Use `--skip-ai` to run scanner only.
2. **AI semantic pass** — fuzzy variants, near-synonyms, abbreviated names. Batches 150 tags at a time (alphabetically sorted to cluster variants). Shows all proposed operations in a numbered table; the `except` option lets you exclude specific row numbers and apply everything else.

---

## Maintenance Commands

| Command | Purpose |
|---------|---------|
| `library-info` | Show library path, book count, calibredb version |
| `clean-identifiers "all"` | Fix malformed identifiers (UUIDs in ID fields, `urnisbn/` format, empty values) |
| `unflag-manual "ids:goodreads:12345"` | Clear the MQG-02 manual flag after manually fixing a book |

---

## Configuration Reference

Full `config.json` structure (copy from `config.example.json`):

```json
{
  "library_path": "/path/to/your/Calibre Library",
  "calibredb_path": "calibredb",

  "ai": {
    "api_key": "",
    "model": "claude-sonnet-4-6",
    "title_author": { "model": "claude-sonnet-4-6" },
    "lcc":          { "model": "claude-sonnet-4-6" },
    "comments":     { "model": "claude-sonnet-4-6" },
    "tags":         { "model": "claude-sonnet-4-6" }
  },

  "identifiers": {
    "fetch_ebook_metadata_path": "",
    "lookup_timeout_seconds": 45,
    "sufficient_types": ["isbn"],
    "mqg_complete_requires": ["grrating", "grvotes"]
  },

  "lcc": {
    "lcc_column": "#lcc",
    "primary_class_column": "#lcc_primary_class",
    "secondary_class_column": "#lcc_secondary_class",
    "lcc_summary_column": "#lcc_summary"
  },

  "comments": {
    "mqg_column": "#mqg_comments",
    "mqg_manual_column": "#mqg_comments_manual",
    "lcc_summary_column": "#lcc_summary"
  },

  "tags": {
    "reviewed_column": "#tags_reviewed",
    "mqg_column": "#mqg_tags",
    "mqg_manual_column": "#mqg_tags_manual"
  },

  "mqg": {
    "title_author_column": "#mqg_title_author",
    "identifiers_column": "#mqg_identifiers",
    "identifiers_manual_column": "#mqg_identifiers_manual",
    "lcc_column": "#mqg_lcc",
    "lcc_manual_column": "#mqg_lcc_manual"
  }
}
```

Set `ai.api_key` once or use the `ANTHROPIC_API_KEY` environment variable.
Per-command `model` overrides inherit the top-level key. `fetch_ebook_metadata_path`
auto-detects from `calibredb_path` when left blank.

---

## Required Calibre Custom Columns

| Column | Lookup name | Type |
|--------|-------------|------|
| LCC Call Number | `#lcc` | Text |
| LCC Primary Class | `#lcc_primary_class` | Enumeration (21 values from `config/lcc-primary-canonical.csv`) |
| LCC Secondary Class | `#lcc_secondary_class` | Enumeration (231 values from `config/lcc-secondary-canonical.csv`) |
| LCC Summary | `#lcc_summary` | Long text (comments) |
| MQG — Title/Author done | `#mqg_title_author` | Yes/No |
| MQG — Identifiers done | `#mqg_identifiers` | Yes/No |
| MQG — Identifiers manual | `#mqg_identifiers_manual` | Yes/No |
| MQG — LCC done | `#mqg_lcc` | Yes/No |
| MQG — LCC manual | `#mqg_lcc_manual` | Yes/No |
| MQG — Comments done | `#mqg_comments` | Yes/No |
| MQG — Comments manual | `#mqg_comments_manual` | Yes/No |
| MQG — Tags done | `#mqg_tags` | Yes/No |
| MQG — Tags manual | `#mqg_tags_manual` | Yes/No |
| Tags reviewed | `#tags_reviewed` | Yes/No |

---

## Project Structure

```
calibre_toolkit/
  cli.py                  Entry point — all commands
  ai.py                   AI client (Anthropic)
  db.py                   Calibre SQLite + calibredb wrapper
  fetcher.py              fetch-ebook-metadata wrapper
  modules/
    lcc.py                MQG-03 LCC enrichment
    comments.py           MQG-04 comments enrichment
    identifiers.py        MQG-02 identifier enrichment
    authors.py            MQG-01 author/title cleanup
    tags.py               MQG-05 tag enrichment + cleanup
    tags_review.py        MQG-05 per-book interactive review
    tag_scanner.py        Deterministic rule set for tags-cleanup
    clean_identifiers.py  Identifier cleanup utility
  services/
    lc_catalog.py         LCCN/ISBN lookups against the LC catalog
  tui/
    app.py                Rich-based TUI menu

config/
  lcc-primary-canonical.csv     21 LCC primary class values
  lcc-secondary-canonical.csv   231 LCC secondary class values

rules/
  lcc.md                  AI prompt rules for LCC enrichment
  comments.md             AI prompt rules for comments enrichment
  reader_profile.md       Reader profile — tone and framing for comments
  author_title.md         AI prompt rules for author/title cleanup
  tags.md                 AI prompt rules for tag enrichment
  tags_cleanup.md         AI prompt rules for the tags-cleanup semantic pass

docs/
  Getting-Started.md      First-time setup guide
  MQG-Pipeline-Overview.md  This file
  archive/                Pre-v1.0 design documents and workflow runbooks
```

---

## Known Limitations

See [ROADMAP.md](../ROADMAP.md) for full detail and planned fixes.

- `#lcc_summary` is AI-drafted from training memory — treat as provisional for obscure books
- Source attribution in AI-only LCC suggestions may name "Library of Congress catalog" even when no catalog record was consulted
- UK and non-US ISBNs typically miss the LC catalog and fall through to AI-only classification
- Step 02 identifier lookups are sequential (5–15s per book); parallelisation is planned
- `tags-cleanup` alphabetical batching may miss cross-batch variant pairs
