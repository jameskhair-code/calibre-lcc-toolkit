# Getting Started — Calibre LCC Toolkit

A step-by-step guide for setting up and running the toolkit for the first time.

---

## Prerequisites

- **Python 3.11 or later**
- **Calibre** installed (the toolkit reads from Calibre's SQLite database and writes via `calibredb`)
- An **Anthropic API key** — the toolkit uses Claude for all AI-assisted steps

---

## Step 1 — Install

Download the ZIP from the GitHub releases page and unzip it, or clone the repository. Then install:

```bash
pip install -e .
```

This installs the `calibre_toolkit` package and its dependencies (Typer, Rich, httpx, anthropic).

---

## Step 2 — Configure

Copy the example config and fill it in:

```bash
cp config.example.json config.json
```

Open `config.json` and set at minimum:

| Key | What to set |
|-----|-------------|
| `library_path` | Full path to your Calibre library folder (the folder containing `metadata.db`) |
| `calibredb_path` | `calibredb` (if on PATH) or the full path to the `calibredb` executable |
| `ai.api_key` | Your Anthropic API key |

The `ai.model` values default to `claude-sonnet-4-6`. Change them if you want to use a different Claude model.

`identifiers.fetch_ebook_metadata_path` can be left blank — it auto-detects from `calibredb_path`. On Windows use full paths: `C:\Program Files\Calibre2\fetch-ebook-metadata.exe`.

> **Tip:** You can also set your API key via the `ANTHROPIC_API_KEY` environment variable instead of putting it in `config.json`.

---

## Step 3 — Create Calibre Custom Columns

The toolkit expects these custom columns to exist in your Calibre library. Create them via **Preferences → Add your own columns** in Calibre:

| Column label | Lookup name | Type | Notes |
|---|---|---|---|
| LCC Call Number | `#lcc` | Text | |
| LCC Primary Class | `#lcc_primary_class` | Enumeration | Load values from `config/lcc-primary-canonical.csv` |
| LCC Secondary Class | `#lcc_secondary_class` | Enumeration | Load values from `config/lcc-secondary-canonical.csv` |
| LCC Summary | `#lcc_summary` | Long text (comments) | |
| MQG — Title/Author done | `#mqg_title_author` | Yes/No | |
| MQG — Identifiers done | `#mqg_identifiers` | Yes/No | |
| MQG — Identifiers manual | `#mqg_identifiers_manual` | Yes/No | |
| MQG — LCC done | `#mqg_lcc` | Yes/No | |
| MQG — LCC manual | `#mqg_lcc_manual` | Yes/No | |
| MQG — Comments done | `#mqg_comments` | Yes/No | |
| MQG — Comments manual | `#mqg_comments_manual` | Yes/No | |
| MQG — Tags done | `#mqg_tags` | Yes/No | |
| MQG — Tags manual | `#mqg_tags_manual` | Yes/No | |
| Tags reviewed | `#tags_reviewed` | Yes/No | |

**For the enumeration columns:** after creating the column, open the column editor and paste the values from the CSV files one per line. There are 21 primary class values and 231 secondary class values.

---

## Step 4 — Launch the TUI

The recommended entry point for interactive use:

```bash
py -m calibre_toolkit.cli menu
```

This opens a Rich-based terminal menu covering all five pipeline steps and maintenance commands. You can also run any step directly from the command line (see the main README for command reference).

---

## Step 5 — Run the Pipeline

The five steps are designed to run in order. Each step marks books complete with a flag column so the next step can filter on it.

| Step | Command | Typical search query |
|------|---------|----------------------|
| MQG-01 | `clean-titles` | `#metadata_queue:true` |
| MQG-02 | `enrich-identifiers` | `#mqg_title_author:true and not #mqg_identifiers:true` |
| MQG-03 | `lcc-enrich` | `#mqg_identifiers:true and not #mqg_lcc:true` |
| MQG-04 | `comments-enrich` | `#mqg_lcc:true and not #mqg_comments:true` |
| MQG-05 | `tags-enrich` | `#mqg_lcc:true and not #mqg_tags:true` |

Each step is **human-in-the-loop**: the AI proposes changes, the tool shows a review table with confidence tiers (● high / ◐ medium / ○ low), and you decide before anything is written to Calibre.

---

## Step 6 — First-Run Tips

- **Always start with a test run:** add `--limit 10 --dry-run` to any command to preview proposals without writing anything.

  ```bash
  py -m calibre_toolkit.cli lcc-enrich "#metadata_queue:true" --limit 10 --dry-run
  ```

- **Use `--limit` to batch your work:** running 20–50 books at a time gives you a manageable review table.

- **The `menu` TUI handles limit prompts:** the "Enrich next N" and "Review next N" buttons prompt you for a count before running.

- **After tags-enrich, run tags-cleanup:** `tags-cleanup` is a separate library-wide normalisation pass that merges variant tags, fixes casing, and drops noise. Run it after you have a full batch of enriched books.

  ```bash
  py -m calibre_toolkit.cli tags-cleanup --skip-ai   # scanner only, free and fast
  py -m calibre_toolkit.cli tags-cleanup              # scanner + AI semantic pass
  ```

- **`library-info` checks your setup:**

  ```bash
  py -m calibre_toolkit.cli library-info
  ```

---

## Known Limitations

See [ROADMAP.md](../ROADMAP.md) for the full list. Key ones for new users:

- `#lcc_summary` is AI-drafted and may be inaccurate for obscure books. A book-description pre-fetch (Google Books / Open Library) is planned to fix this.
- UK and non-US ISBNs often miss the LC catalog and fall through to AI-only classification. An ISBN cross-reference cascade via Open Library is planned.
- Step 02 identifier lookups are sequential and slow on large batches (5–15s per book). Parallelisation is planned.
