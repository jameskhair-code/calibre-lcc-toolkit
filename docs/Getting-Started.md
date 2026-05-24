# Getting Started — Calibre Metadata Toolkit

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

The fastest path is the interactive wizard:

```bash
py -m calibre_toolkit.cli init
```

`init` prompts for your library path, verifies `calibredb` runs, tests your Anthropic API key with a minimal call, and writes a complete `config.json` atomically.

If you prefer to edit JSON by hand, copy the example instead:

```bash
cp config.example.json config.json
```

and set at minimum:

| Key | What to set |
|-----|-------------|
| `library_path` | Full path to your Calibre library folder (the folder containing `metadata.db`) |
| `calibredb_path` | `calibredb` (if on PATH) or the full path to the `calibredb` executable |
| `ai.api_key` | Your Anthropic API key |

The `ai.model` values default to the alias `latest`. The supported aliases are:

| Alias    | Resolves to                  | Use when                                                  |
|----------|------------------------------|-----------------------------------------------------------|
| `fast`   | the latest Haiku model       | speed and cost matter more than nuance                    |
| `latest` | the newest recommended model | normal operation (default)                                |
| `legacy` | `claude-sonnet-4-6`          | reproducibility — pin to the model used at v1.0/v1.1 ship |

You can also pass a literal Anthropic model ID (e.g. `claude-sonnet-4-6` or any current ID); it is forwarded to the API unchanged. When Anthropic ships a new generation we update `calibre_toolkit/models.py` and the alias rolls forward — no config edits required.

`--ai-model <alias>` works on every AI step and overrides the config for that run.

`identifiers.fetch_ebook_metadata_path` can be left blank — it auto-detects from `calibredb_path`. On Windows use full paths: `C:\Program Files\Calibre2\fetch-ebook-metadata.exe`.

> **Tip:** You can also set your API key via the `ANTHROPIC_API_KEY` environment variable instead of putting it in `config.json`.

---

## Step 3 — Create Calibre Custom Columns

The toolkit expects 14 custom columns to exist in your Calibre library. Close Calibre, then run:

```bash
py -m calibre_toolkit.cli setup-columns
```

This creates any missing columns via `calibredb add_custom_column` and loads the LCC enumeration values from `config/lcc-*-canonical.csv`. It is idempotent — re-running it skips columns that already exist with the right type.

To create them by hand instead, use **Preferences → Add your own columns** in Calibre:

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

## Step 3a — Verify with `doctor`

After `init` and `setup-columns`, confirm everything is wired up:

```bash
py -m calibre_toolkit.cli doctor
```

`doctor` is a read-only validation pass: config parses and has required keys, `metadata.db` exists at `library_path`, `calibredb --version` runs, the Anthropic API key authenticates, and every required custom column exists with the expected datatype. It exits non-zero on any failure, so you can wire it into a CI gate.

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

### Tier defaults at the bulk-approval prompt

Every AI-confidence step (clean-titles, enrich-identifiers, lcc-enrich, comments-enrich, tags-enrich) groups proposals by confidence and offers a bulk choice per tier. The defaults — applied if you press Enter — are:

| Tier | Default action | What it does |
|------|----------------|--------------|
| **high** (●)   | `all`    | Apply every high-confidence proposal in one shot |
| **medium** (◐) | `review` | Step through each book individually |
| **low** (○)    | `skip`   | Do not apply; leave for a future pass |

Pass `--auto-apply-high` to skip the prompt entirely for the high tier — useful when you trust the model's confidence calibration and want to power through a large batch.

### Flag conventions

Across commands the canonical names for review flags are:

- `--auto-apply-high` — apply high-confidence proposals without prompting (was `--auto-approve` on `tags-review` before v1.1).
- `--force` — re-process books normally skipped; each command's `--help` describes what is overridden (was `--force-lookup` on `enrich-identifiers`).
- `--dry-run` — preview proposed changes without writing.

Old flag names still work but print a one-line deprecation notice.

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
