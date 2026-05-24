"""
Model alias layer.

Before v1.2 item 9, the model ID `claude-sonnet-4-6` was hardcoded in
`ai.py` and `config.example.json`. Every time Anthropic shipped a new
generation, every user had to hand-edit their `config.json`.

This module introduces three named aliases — `fast`, `latest`, and
`legacy` — plus a deprecation table that maps retired model IDs to
their recommended replacements. The resolver is intentionally
permissive: anything that is not a known alias falls through unchanged,
so a literal model ID like `claude-sonnet-4-6` keeps working exactly
as before.

When Anthropic publishes a new model, the only edit required is one
line in `_ALIAS_MAP`.

Doc:
    /docs/Getting-Started.md — "Model aliases" section
"""

from __future__ import annotations

from dataclasses import dataclass

from .logging_config import get_logger

_log = get_logger(__name__)


# ── Alias table ────────────────────────────────────────────────────────────

# The single source of truth. Each entry maps an alias to a concrete model
# ID at the current moment in time. The shape is two columns so swapping
# the latest model is a one-line edit when a new generation ships.
_ALIAS_MAP: dict[str, str] = {
    "fast":   "claude-haiku-4-5-20251001",
    "latest": "claude-opus-4-7",
    "legacy": "claude-sonnet-4-6",
}

# Aliases that previously meant something different. None today.
# When `latest` rolls forward, the previous concrete ID can be aliased
# here so users who pinned the old name see a deprecation warning.
_DEPRECATED_ALIASES: dict[str, str] = {}

# Direct model-ID deprecations. Keys are full Anthropic model IDs that
# users may have hardcoded in older configs; values are the recommended
# replacement. The resolver passes the key through to the SDK unchanged
# (so anyone who pinned a specific ID for reproducibility keeps working)
# but logs a one-time warning so the user knows it's time to switch.
_DEPRECATED_MODELS: dict[str, str] = {
    # Add entries here as Anthropic retires model IDs. Example shape:
    #   "claude-sonnet-3-5": "claude-sonnet-4-6",
}


# ── Public API ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResolvedModel:
    """The outcome of resolving a user-supplied model token.

    `model_id` is the literal string passed to the Anthropic SDK. `alias`
    is the alias name the user typed (or None if they passed a full ID).
    `deprecation_note` is set when the resolver picked up a deprecated
    alias or model ID — used to show a one-line warning at run start.
    """
    model_id: str
    alias: str | None = None
    deprecation_note: str | None = None


def list_aliases() -> dict[str, str]:
    """Return a copy of the alias map. Useful for --help text and docs."""
    return dict(_ALIAS_MAP)


def resolve_model(token: str | None) -> ResolvedModel:
    """Resolve a user token to a concrete Anthropic model ID.

    The resolver accepts:
      - one of the alias names in `_ALIAS_MAP` (`fast`, `latest`, `legacy`),
      - a full model ID (passed through unchanged), or
      - None / empty string (defaults to the `latest` alias).

    Anything else is passed through so users on pre-release IDs aren't
    blocked. The deprecation table is consulted for both alias and
    full-ID inputs.
    """
    if token is None or not str(token).strip():
        alias = "latest"
        model_id = _ALIAS_MAP[alias]
        return ResolvedModel(model_id=model_id, alias=alias)

    name = str(token).strip().lower()

    if name in _ALIAS_MAP:
        return ResolvedModel(model_id=_ALIAS_MAP[name], alias=name)

    if name in _DEPRECATED_ALIASES:
        replacement = _DEPRECATED_ALIASES[name]
        model_id = _ALIAS_MAP.get(replacement, replacement)
        note = (
            f"alias {token!r} is deprecated; use {replacement!r} instead "
            f"(resolved to {model_id})"
        )
        _log.warning(note)
        return ResolvedModel(
            model_id=model_id, alias=replacement, deprecation_note=note,
        )

    # Full model ID. Pass through; warn if Anthropic has retired it.
    raw = str(token).strip()
    if raw in _DEPRECATED_MODELS:
        replacement = _DEPRECATED_MODELS[raw]
        note = (
            f"model {raw!r} is deprecated; recommended replacement is "
            f"{replacement!r}. Update your config or use --ai-model latest."
        )
        _log.warning(note)
        return ResolvedModel(
            model_id=raw, alias=None, deprecation_note=note,
        )

    return ResolvedModel(model_id=raw, alias=None)
