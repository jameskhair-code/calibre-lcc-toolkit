# Calibre LCC Toolkit

An AI-assisted Python CLI for enriching Calibre library metadata. Built for a personal collection of literary awards and nominees (~5,000 books).

---

## Overview

The toolkit runs a structured enrichment pipeline ("MQG") across five metadata areas:

| Step | Command | What it does |
|------|---------|--------------|
| MQG-01 | `clean-titles` | AI-assisted author and title normalization |
| MQG-02 | `enrich-identifiers` | Finds and adds ISBNs, Goodreads IDs, Amazon IDs |
| MQG-03 | `lcc-enrich` | Library of Congress Classification — call number, primary class, secondary class, subject summary |
| MQG-04 | `comments-enrich` | AI-generated book description with 6 structured sections |
| MQG-05 | `tags-enrich` | AI-assisted subject tag enrichment — Form, Subject, Period, Geography |

Each step is human-in-the-loop: the AI proposes, the tool displays a review table, and you decide before anything is written to Calibre. A `menu` command launches a TUI covering every step and maintenance command.

---

## Setup

**Requirements:** Python 3.11+, Calibre installed

```bash
pip install -e .
```

Copy `config.example.json` to `config.json` and fill in your library path, calibredb path, and API key(s).

---

## Configuration

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

The toolkit is Anthropic-only. Set `ai.api_key` once (or via the `ANTHROPIC_API_KEY` environment variable). Per-command blocks (`ai.lcc`, `ai.tags`, etc.) only need a `model` — they inherit the top-level key. Provide a separate `api_key` in a per-command block only if you want a different key for that command.

`fetch_ebook_metadata_path` can be left blank to auto-detect from `calibredb_path`. On Windows use full paths (e.g. `C:\Program Files\Calibre2\calibredb.exe`).

---

## Commands

All commands are run as:

```bash
py -m calibre_toolkit.cli <command> [options]
```

### `lcc-enrich`

AI-assisted Library of Congress Classification enrichment.

```bash
# Normal run
py -m calibre_toolkit.cli lcc-enrich "#mqg_identifiers:true and not #mqg_lcc:true"

# Limit to 10 books for testing
py -m calibre_toolkit.cli lcc-enrich "#metadata_queue:true" --limit 10

# Re-process already-populated books
py -m calibre_toolkit.cli lcc-enrich "#metadata_queue:true" --force

# Audit mode — compare AI proposals to current values, no writes
py -m calibre_toolkit.cli lcc-enrich "#lcc:true" --dry-run --force --limit 20

# Override AI provider for a single run (A/B testing)
py -m calibre_toolkit.cli lcc-enrich "#metadata_queue:true" --dry-run --ai-provider openai --ai-model gpt-4o
```

Populates four Calibre fields per book:

| Field | Description |
|-------|-------------|
| `#lcc` | LCC call number (e.g. `UA23 .J255 2024`) |
| `#lcc_primary_class` | Top-level class drop-down (e.g. `U - Military Science`) |
| `#lcc_secondary_class` | Subclass drop-down (e.g. `UA - Armies & Military Organization`) |
| `#lcc_summary` | One-sentence subject summary |

Drop-down values are validated against canonical CSVs in `config/`. Confidence is displayed per book (● high / ◐ medium / ○ low) and you confirm before any writes occur.

### `enrich-identifiers`

Finds and adds external identifiers (ISBN, Goodreads, Amazon, etc.) using Calibre's own `fetch-ebook-metadata` tool.

```bash
py -m calibre_toolkit.cli enrich-identifiers "#metadata_queue:true"
py -m calibre_toolkit.cli enrich-identifiers "#mqg_title_author:true" --batch-size 10
```

### `clean-titles`

AI-assisted author and title normalization.

```bash
py -m calibre_toolkit.cli clean-titles "tag:booker"
py -m calibre_toolkit.cli clean-titles "series:Man Booker Prize" --auto-apply-high
```

### `comments-enrich`

AI-assisted book comments / description enrichment.

```bash
# Tone test — 3 voice variants for one book, no writes
py -m calibre_toolkit.cli comments-enrich "#mqg_lcc:true" --tone-test

# Dry run — see proposed comments without writing
py -m calibre_toolkit.cli comments-enrich "#mqg_lcc:true" --limit 5 --dry-run

# Normal run
py -m calibre_toolkit.cli comments-enrich "#mqg_lcc:true and not #mqg_comments:true"

# Re-process books that already have comments
py -m calibre_toolkit.cli comments-enrich "#mqg_lcc:true" --force --limit 10
```

Generates a structured HTML comment with six sections:

| Section | Description |
|---------|-------------|
| The Book | What it is and its core argument (2–4 sentences) |
| Why It Matters | Its significance in its field |
| Award Context | Award(s), year, won/shortlisted |
| Something You Might Not Know | (Conditional) Surprising or memorable fact |
| Why Read It | The honest sell |
| Source Notes | AI transparency |

Tone is set in `rules/reader_profile.md`. Use `--tone-test` to compare three voice registers (witty-opinionated, neutral-professional, warm-accessible) before committing.

Config block (add to config.json):

```json
"comments": {
  "mqg_column": "#mqg_comments",
  "mqg_manual_column": "#mqg_comments_manual",
  "lcc_summary_column": "#lcc_summary"
}
```

To use a different model for comments specifically, set `ai.comments.model` in `config.json` (already included in the config template above).

### `tags-enrich`

AI-assisted subject tag enrichment. Generates 4–8 flat tags per book across Form, Subject, Period, and Geography categories.

```bash
# Dry run — preview proposed tags without writing
py -m calibre_toolkit.cli tags-enrich "#mqg_lcc:true" --limit 10 --dry-run

# Normal run
py -m calibre_toolkit.cli tags-enrich "#mqg_lcc:true and not #mqg_tags:true"
```

Validation runs after every AI response: 4-word cap (silently truncated), no commas (split on first), exactly one Form tag per book (confidence drops to medium with a diagnostic note if violated). LCC fields, when present, are passed in as context.

Config block (add to config.json):

```json
"tags": {
  "reviewed_column": "#tags_reviewed",
  "mqg_column": "#mqg_tags",
  "mqg_manual_column": "#mqg_tags_manual"
}
```

### `tags-cleanup`

Library-wide tag vocabulary normalisation. Two passes:

1. **Deterministic scanner.** LCSH date+name drops, bare date ranges, Calibre taxonomy noise, date-range → period-name lookups, formatting cleanup. No AI call.
2. **AI semantic pass.** Fuzzy variant matches and near-synonyms the scanner cannot resolve. Skip with `--skip-ai` for scanner-only runs.

Operations are grouped by pattern with bulk approval per group; safe groups default to "apply all", everything else defaults to "review". The apply prompt also accepts `except` — enter the row numbers to skip (e.g. `7 12 15`) and everything else applies in one shot.

```bash
# Audit only
py -m calibre_toolkit.cli tags-cleanup --dry-run

# Scanner-only run (no AI cost)
py -m calibre_toolkit.cli tags-cleanup --skip-ai

# Ignore long-tail tags during the AI pass
py -m calibre_toolkit.cli tags-cleanup --min-books 2
```

### `tags-review`

Per-book interactive tag review. Shows current vs. AI-proposed tags with **[a]** approve / **[k]** keep / **[e]** edit / **[s]** skip controls. Sets `#tags_reviewed` per locked book.

```bash
py -m calibre_toolkit.cli tags-review
py -m calibre_toolkit.cli tags-review "tag:Booker" --limit 20
py -m calibre_toolkit.cli tags-review --auto-approve --limit 100
```

### `menu`

Launches a Rich-based TUI covering every pipeline step and maintenance command. Recommended entry point for interactive sessions.

```bash
py -m calibre_toolkit.cli menu
```

### `clean-identifiers`

Scans and fixes malformed identifiers (UUIDs in identifier fields, `urnisbn/` format, empty values).

```bash
py -m calibre_toolkit.cli clean-identifiers "all"
```

### `library-info`

Shows library path, book counts, and calibredb version. Useful for diagnosing search-scope discrepancies.

```bash
py -m calibre_toolkit.cli library-info
```

### `unflag-manual`

Clears the MQG-02 manual-curation flag after you have fixed a book manually.

```bash
py -m calibre_toolkit.cli unflag-manual "ids:goodreads:12345"
```

---

## Calibre Custom Columns

The toolkit expects these custom columns to exist in your Calibre library:

| Column | Type | Purpose |
|--------|------|---------|
| `#lcc` | Text | LCC call number |
| `#lcc_primary_class` | Enumeration | Primary LCC class |
| `#lcc_secondary_class` | Enumeration | Secondary LCC subclass |
| `#lcc_summary` | Long text | One-sentence subject summary |
| `#mqg_lcc` | Yes/No | MQG-03 completion flag |
| `#mqg_lcc_manual` | Yes/No | Manual review flag for LCC |
| `#mqg_comments` | Yes/No | MQG-04 completion flag |
| `#mqg_comments_manual` | Yes/No | Manual review flag for comments |
| `#mqg_identifiers` | Yes/No | MQG-02 completion flag |
| `#mqg_identifiers_manual` | Yes/No | Manual review flag for identifiers |
| `#mqg_title_author` | Yes/No | MQG-01 completion flag |
| `#mqg_tags` | Yes/No | MQG-05 completion flag |
| `#mqg_tags_manual` | Yes/No | Manual review flag for tags |
| `#tags_reviewed` | Yes/No | Per-book lock set by `tags-review` |

Enumeration values for `#lcc_primary_class` and `#lcc_secondary_class` are defined in `config/lcc-primary-canonical.csv` and `config/lcc-secondary-canonical.csv`.

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
    app.py                Rich-based TUI menu (launched by `menu` command)

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
```
