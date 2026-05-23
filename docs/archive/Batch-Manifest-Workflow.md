# Batch Manifest Workflow

The batch manifest workflow provides a standard way to define a stable set of Calibre records for toolkit processing.

## Purpose

Use Calibre to discover the records you want to process, then freeze that selection into a manifest CSV. The manifest becomes the durable record of the batch so downstream module work is not affected if Calibre metadata changes later.

```text
Calibre search string / IDs / ID file
        -> batch manifest CSV
        -> module exports and reports use the manifest's CalibreId column
```

## Launcher option

Use:

```text
B1. Batch: Create batch manifest
```

The launcher prompts for:

- Batch slug
- Calibre search string
- Explicit Calibre IDs
- Optional Calibre ID file
- Optional exact Award Programs filter
- Output batch manifest CSV
- Batch selection summary CSV
- Optional Calibre library path

## Recommended operating pattern

1. Build and test a search in Calibre until the visible result set is correct.
2. Copy the Calibre search string.
3. Run `B1. Batch: Create batch manifest`.
4. Save the manifest in `./input` using a meaningful batch slug.
5. Use the manifest's `CalibreId` column for later module work.

## Supported selection methods

### Search only

Use this for normal planned batches.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\New-ToolkitBatchManifest.ps1 `
  -BatchSlug "french-history-title-author" `
  -Search '#mqg_title_author:false and tags:"French History"' `
  -OutputCsv ".\input\batch-french-history-title-author.csv" `
  -ReportCsv ".\reports\batch-french-history-title-author-selection-summary.csv"
```

### Explicit IDs only

Use this for small hand-picked batches.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\New-ToolkitBatchManifest.ps1 `
  -BatchSlug "leo-gershoy-smoketest" `
  -CalibreIds "5374,5375,5376" `
  -OutputCsv ".\input\batch-leo-gershoy-smoketest.csv"
```

### ID file

Use this when you want to preserve a simple reusable list of IDs.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\New-ToolkitBatchManifest.ps1 `
  -BatchSlug "selected-history-books" `
  -CalibreIdFile ".\input\batch-ids-selected-history-books.txt" `
  -OutputCsv ".\input\batch-selected-history-books.csv"
```

The ID file may contain one ID per line or comma/space/semicolon-separated IDs. Lines may include comments after `#`.

## Manifest columns

The manifest includes:

- `BatchSlug`
- `CalibreId`
- `Title`
- `Authors`
- `ISBN`
- `Identifiers`
- `Publisher`
- `Published`
- `AwardPrograms`
- LCC fields
- MQG checkbox states
- Source selection fields
- `ExportedAt`

## Safety notes

This workflow is read-only. It does not modify Calibre metadata. By default, the script refuses to overwrite an existing manifest or summary report unless `-Overwrite` is supplied or the launcher overwrite prompt is confirmed with `YES`.

If both a search string and explicit IDs are provided, the explicit IDs are treated as an intersection/filter against the search results. This is useful when you want to narrow a larger search result set.

Downstream scripts do not yet all accept `-BatchManifest` directly. Until direct support is added, use the manifest's `CalibreId` column as the stable source for module-specific ID inputs.
