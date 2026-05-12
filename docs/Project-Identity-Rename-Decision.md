# Project Identity and Rename Decision - v0.12.0

## Purpose

This document captures the naming and identity direction for the toolkit.

The project began as a Library of Congress Classification helper and is still historically named `calibre-lcc-toolkit` in the GitHub repository, local folder, launcher filename, configuration, and many script names.

The project has now grown into a broader Calibre metadata workflow system. Its visible product identity should shift to:

Calibre Metadata Toolkit

The goal is to rename the product experience without breaking existing paths, aliases, scripts, or Git workflow.

## Current Identity

Historical / implementation identity:

- GitHub repository: `calibre-lcc-toolkit`
- Local folder: `lcc-toolkit`
- Launcher script: `Start-LccWorkflow.ps1`
- Config file: `config/lcc-toolkit.config.json`
- Visible launcher header as of v0.11.0: `Calibre LCC Toolkit`
- Many scripts and functions still use LCC-oriented names because LCC was the original workflow foundation.

Current product reality:

- The toolkit now supports multiple metadata quality gates.
- The toolkit includes Author/Title cleanup, Identifiers, LCC, Comments, MQG completion workflows, batch manifests, reports, and safety validation.
- The future roadmap includes guided workflows for Comments and Tags.
- LCC remains important, but it is no longer the whole product.

## Decision

The visible product name will become:

Calibre Metadata Toolkit

The historical repo, folder, launcher filename, and many implementation names will remain temporarily for compatibility.

This is an intentional compatibility state, not the final naming model.

## Why Not Big-Bang Rename Now

A full rename would touch many layers at once:

- GitHub repository name,
- local folder path,
- shell aliases such as `ctk`,
- launcher filename,
- config filename,
- documentation references,
- script names,
- function names,
- changelog wording,
- internal report names,
- Cursor workspace references,
- any user shortcuts or habits.

Renaming everything at once creates unnecessary operational risk.

The tool is entering a productive-use redesign phase. The priority is to improve the user-facing workflow and operator experience first.

## Rename Strategy

Use a staged rename.

### Stage 1 - Product Branding Layer

Update visible user-facing language where safe.

Examples:

- launcher title/header,
- documentation titles,
- README/orientation docs,
- changelog wording,
- future user-facing workflow labels.

Do not rename files or folders in this stage unless there is a clear low-risk reason.

### Stage 2 - Compatibility Launcher

Introduce a new preferred launcher later, for example:

- `Start-CalibreMetadataToolkit.ps1`

Keep the old launcher as a compatibility wrapper:

- `Start-LccWorkflow.ps1`

The old launcher can call the new launcher so existing habits and aliases do not break immediately.

### Stage 3 - Config and Script Naming Cleanup

After the productive launcher is stable, consider renaming configuration and scripts where useful.

Potential future examples:

- `config/calibre-metadata-toolkit.config.json`
- `Start-CalibreMetadataToolkit.ps1`
- documentation that treats LCC as one workflow inside the larger product.

This should be done carefully and only after compatibility paths exist.

### Stage 4 - Repo and Folder Rename

Do not rename the GitHub repository or local folder yet.

Potential future state:

- repo: `calibre-metadata-toolkit`
- folder: `calibre-metadata-toolkit`

This should wait until the product identity is stable and the user is ready to update local paths, remotes, aliases, and workspaces.

## Compatibility Rule

Any rename should preserve old entry points when practical.

The user should not lose the ability to run the toolkit through existing habits such as:

- opening the current local folder,
- running `ctk`,
- running `Start-LccWorkflow.ps1`.

New names should be introduced as preferred paths before old paths are removed.

## LCC Naming Rule

LCC remains a valid workflow name.

Do not remove LCC wording where it specifically refers to the MQG-03 LCC classification workflow.

Examples that should remain LCC-specific:

- LCC import/export scripts,
- LCC classification documentation,
- LCC workflow labels,
- reports specifically about LCC fields.

The rename is about the overall product identity, not erasing the LCC module.

## Documentation Direction

The primary documentation should refer to the product as:

Calibre Metadata Toolkit

It may include a compatibility note:

Formerly / historically implemented as `calibre-lcc-toolkit`.

The documentation should clearly explain that LCC is one core workflow within the broader metadata toolkit.

## Recommended v0.12.0 Scope

For v0.12.0:

1. Capture this rename decision.
2. Begin using Calibre Metadata Toolkit in new design documents.
3. Do not rename repo/folder yet.
4. Do not rename launcher file yet.
5. Consider changing only the visible launcher header in a future implementation release.
6. Preserve compatibility with current `ctk` usage.

## Future Preferred Naming

Preferred product name:

Calibre Metadata Toolkit

Potential future launcher:

Start-CalibreMetadataToolkit.ps1

Potential future repo/folder name:

calibre-metadata-toolkit

Potential compatibility launcher:

Start-LccWorkflow.ps1, preserved as wrapper or legacy entry point.

## Risks

Risks of moving too fast:

- broken local paths,
- broken aliases,
- broken docs,
- broken scripts,
- confusion between old and new names,
- GitHub remote confusion,
- unnecessary churn while the productive launcher is still evolving.

Risks of moving too slowly:

- user-facing identity remains confusing,
- documentation keeps reinforcing the old LCC-only mental model,
- new workflows feel bolted onto the wrong product shell.

## Decision Summary

Use the new product name now in documentation and future user-facing design:

Calibre Metadata Toolkit

Keep current implementation names temporarily:

- repo: `calibre-lcc-toolkit`,
- folder: `lcc-toolkit`,
- launcher: `Start-LccWorkflow.ps1`,
- config: `lcc-toolkit.config.json`.

Do not perform a big-bang rename.

Plan a staged compatibility-first rename after the productive launcher and target-selection model are stable.

## Status

Status: Draft decision for v0.12.0.

Next action:

Review this decision, then decide whether v0.12.0 should also add a lightweight primary README/orientation document.
