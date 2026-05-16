# Calibre LCC Toolkit

An AI-assisted Python CLI for enriching Calibre library metadata. Built for a personal collection of literary awards and nominees (~5,000 books).

---

## Overview

The toolkit runs a structured enrichment pipeline ("MQG") across four metadata areas:

| Step | Command | What it does |
|------|---------|--------------|
| MQG-01 | `clean-titles` | AI-assisted author and title normalization |
| MQG-02 | `enrich-identifiers` | Finds and adds ISBNs, Goodreads IDs, Amazon IDs |
| MQG-03 | `lcc-enrich` | Library of Congress Classification — call number, primary class, secondary class, subject summary |
| MQG-04 | `comments-enrich` | AI-generated book description with 6 structured sections |

Each step is human-in-the-loop: the AI proposes, the tool displays a review table, and you decide before anything is written to Calibre.

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
  "library_path": "path/to/your/Calibre Library",
  "calibredb_path": "path/to/calibredb",
  "ai": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "api_key": "",
    "lcc": {
      "provider": "anthropic",
      "model": "claude-sonnet-4-6",
      "api_key": ""
    }
  },
  "identifiers": {
    "fetch_ebook_metadata_path": "path/to/fetch-ebook-metadata",
    "lookup_timeout_seconds": 45,
    "sufficient_types": ["isbn"],
    "mqg_complete_requires": ["grrating", "grvotes"]
  },
  "mqg": {
    "title_author_column": "#mqg_title_author",
    "identifiers_column": "#mqg_identifiers",
    "identifiers_manual_column": "#mqg_identifiers_manual",
    "lcc_column": "#mqg_lcc",
    "lcc_manual_column": "#mqg_lcc_manual"
  },
  "lcc": {
    "lcc_column": "#lcc",
    "primary_class_column": "#lcc_primary_class",
    "secondary_class_column": "#lcc_secondary_class",
    "lcc_summary_column": "#lcc_summary"
  }
}
```

The `ai.lcc` block is optional — it lets you use a different provider or model for LCC enrichment specifically. Any key not set in the override block falls back to the top-level `ai` block.

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

AI override (optional, add inside the `ai` block):

```json
"comments": {
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "api_key": ""
}
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

Enumeration values for `#lcc_primary_class` and `#lcc_secondary_class` are defined in `config/lcc-primary-canonical.csv` and `config/lcc-secondary-canonical.csv`.

---

## Project Structure

```
calibre_toolkit/
  cli.py                  Entry point — all commands
  ai.py                   AI client (OpenAI + Anthropic)
  db.py                   Calibre SQLite + calibredb wrapper
  fetcher.py              fetch-ebook-metadata wrapper
  modules/
    lcc.py                MQG-03 LCC enrichment
    comments.py           MQG-04 comments enrichment
    identifiers.py        MQG-02 identifier enrichment
    authors.py            MQG-01 author/title cleanup
    clean_identifiers.py  Identifier cleanup utility

config/
  lcc-primary-canonical.csv     21 LCC primary class values
  lcc-secondary-canonical.csv   231 LCC secondary class values

rules/
  lcc.md                  AI prompt rules for LCC enrichment
  comments.md             AI prompt rules for comments enrichment
  reader_profile.md       Reader profile — tone and framing for comments
  author_title.md         AI prompt rules for author/title cleanup
```
