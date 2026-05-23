# MQG-03 LCC Enrichment

## What it does

For each book, the AI looks up the Library of Congress catalog and proposes:

| Field | Calibre column | Description |
|-------|---------------|-------------|
| Call number | `#lcc` | Full LCC call number, e.g. `UA23 .J255 2024` |
| Primary class | `#lcc_primary_class` | Top-level class, e.g. `U - Military Science` |
| Secondary class | `#lcc_secondary_class` | Subclass, e.g. `UA - Armies & Military Organization` |
| Subject summary | `#lcc_summary` | One-sentence description of what the book is specifically about |

Primary and secondary class are **derived from the call number** by the code, not chosen by the AI. They are then validated against the canonical CSVs. The AI only proposes the call number and subject summary.

---

## Confidence levels

| Symbol | Level | Meaning |
|--------|-------|---------|
| ● | High | Catalog-confirmed for this edition (ISBN match to LC record) |
| ◐ | Medium | WorldCat consensus across multiple library records |
| ○ | Low | Schedule-derived or ambiguous; no catalog confirmation |

---

## Common commands

```bash
# Standard enrichment run
py -m calibre_toolkit.cli lcc-enrich "#mqg_identifiers:true and not #mqg_lcc:true"

# Test run — 10 books, asks before writing
py -m calibre_toolkit.cli lcc-enrich "#metadata_queue:true" --limit 10

# Re-process books that already have all four fields
py -m calibre_toolkit.cli lcc-enrich "#metadata_queue:true" --force

# Audit mode — see what AI would write vs. what's currently in Calibre, no writes
py -m calibre_toolkit.cli lcc-enrich "#lcc:true" --dry-run --force --limit 20
```

---

## Canonical values

Drop-down values are loaded from:

- `config/lcc-primary-canonical.csv` — 21 primary class values
- `config/lcc-secondary-canonical.csv` — 231 secondary class values

Format rules: `&` throughout (not `/` or `and`), no commas within values, no slashes.

If the AI returns a primary or secondary value not in the canonical list, the tool flags a validation warning and shows it in the review table before prompting.

---

## Subject summary field (`#lcc_summary`)

A one-sentence plain-prose description of what the book is specifically about, starting where the primary and secondary class leave off. It does not repeat the broad LCC category — it goes straight to the specific subject, argument, period, or geography that distinguishes this book.

Time period and geography are included only when they are genuinely distinctive and not already implied by the secondary class.

**Examples:**

> Chronicles the American campaign to eradicate poliomyelitis, focusing on the rivalry between Jonas Salk and Albert Sabin and the 1954 field trial of the Salk vaccine.

> Traces three centuries of German drainage, river engineering, and land reclamation projects, arguing that the conquest of wetlands and waterways was central to the making of modern German national identity.

> A nuclear war planner's insider account of Cold War U.S. first-strike strategy, exposing the secret doomsday command-and-control system built for large-scale nuclear conflict.

---

## AI configuration

LCC enrichment uses the `ai.lcc` block in config.json, which overrides the top-level `ai` block. This allows a different provider or model for LCC without affecting other commands.

```json
"ai": {
  "provider": "openai",
  "model": "gpt-4o-mini",
  "api_key": "",
  "lcc": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "api_key": ""
  }
}
```

To run with a different provider for a single session without editing config:

```bash
py -m calibre_toolkit.cli lcc-enrich "..." --ai-provider openai --ai-model gpt-4o
```
