"""Per-command Typer handlers + orchestration.

One module per CLI command (v1.9 item 1). Each module registers its
handlers on the shared `app` in `_common.py` as an import side-effect;
`cli.py` imports every module here in help-listing order. Orchestration
(prompts, Calibre writes, review/apply flow) lives in these modules;
pure domain logic stays in `calibre_toolkit/modules/`.
"""
