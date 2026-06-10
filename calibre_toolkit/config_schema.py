"""Typed validation for config.json (v1.9 item 6).

ToolkitConfig mirrors config.example.json exactly — same field names, same
JSON shape. It is a *validator*, not the runtime object: the loaders call
`validate_config(raw)` and keep passing the original parsed dict through,
so every access-site `.get` default and cross-block fallback (e.g.
description → catalog timeouts) fires exactly as before. The model's job is
to make a malformed config fail loudly at startup with field-precise
messages instead of a KeyError or ValueError deep in a run.

Key policy:
- `library_path` is the only required field — everything else is defaulted
  at its access site today and the model must not change that.
- Keys starting with `_` are silently ignored at every level (the
  config.example.json comment convention).
- Other unknown keys are returned as warnings, not rejected — a typo'd key
  should be visible at startup, but a key from a future toolkit version
  must not crash this one.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, ValidationError


class ConfigValidationError(Exception):
    """Raised when config.json fails schema validation.

    `errors` is a list of human-readable, field-precise lines, e.g.
    "ai.request_timeout_seconds: Input should be a valid number".
    """

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class _Section(BaseModel):
    # extra="allow" so unknown keys survive into model_extra, where the
    # post-validation walk turns the non-underscore ones into warnings.
    model_config = ConfigDict(extra="allow")


class AiOverride(_Section):
    """Shape shared by the top-level `ai` block and its per-command
    override blocks — the runtime merges them with {**base, **override}."""
    api_key: Optional[str] = None
    model: Optional[str] = None
    request_timeout_seconds: Optional[float] = None
    max_retries: Optional[int] = None


class AiConfig(AiOverride):
    title_author: Optional[AiOverride] = None
    lcc: Optional[AiOverride] = None
    comments: Optional[AiOverride] = None
    tags: Optional[AiOverride] = None


class IdentifiersConfig(_Section):
    fetch_ebook_metadata_path: Optional[str] = None
    lookup_timeout_seconds: Optional[float] = None
    max_workers: Optional[int] = None
    sufficient_types: Optional[list[str]] = None
    mqg_complete_requires: Optional[list[str]] = None


class HttpConfig(_Section):
    """Shared shape of the `fetcher` and `catalog` blocks."""
    request_timeout_seconds: Optional[float] = None
    max_retries: Optional[int] = None


class DescriptionConfig(HttpConfig):
    google_books_api_key: Optional[str] = None


class LccConfig(_Section):
    lcc_column: Optional[str] = None
    primary_class_column: Optional[str] = None
    secondary_class_column: Optional[str] = None
    lcc_summary_column: Optional[str] = None


class CommentsConfig(_Section):
    mqg_column: Optional[str] = None
    mqg_manual_column: Optional[str] = None
    lcc_summary_column: Optional[str] = None


class TagsConfig(_Section):
    reviewed_column: Optional[str] = None
    mqg_column: Optional[str] = None
    mqg_manual_column: Optional[str] = None


class MqgConfig(_Section):
    title_author_column: Optional[str] = None
    identifiers_column: Optional[str] = None
    identifiers_manual_column: Optional[str] = None
    lcc_column: Optional[str] = None
    lcc_manual_column: Optional[str] = None


class ReviewConfig(_Section):
    apply_confirm_threshold: Optional[int] = None


class ToolkitConfig(_Section):
    library_path: str
    # Optional to follow runtime truth (every access site defaults to
    # "calibredb"); doctor's stricter missing=fail check is deliberately
    # left alone.
    calibredb_path: Optional[str] = None
    ai: Optional[AiConfig] = None
    identifiers: Optional[IdentifiersConfig] = None
    fetcher: Optional[HttpConfig] = None
    catalog: Optional[HttpConfig] = None
    description: Optional[DescriptionConfig] = None
    lcc: Optional[LccConfig] = None
    comments: Optional[CommentsConfig] = None
    tags: Optional[TagsConfig] = None
    mqg: Optional[MqgConfig] = None
    review: Optional[ReviewConfig] = None


def _format_errors(e: ValidationError) -> list[str]:
    lines = []
    for err in e.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(top level)"
        line = f"{loc}: {err['msg']}"
        # Echo the offending input for context — except anything that looks
        # like a credential, which must never land in terminal output.
        if "key" not in loc.lower():
            got = err.get("input")
            if got is not None and not isinstance(got, (dict, list)):
                line += f" (got {got!r})"
        lines.append(line)
    return lines


def _collect_unknown_keys(model: BaseModel, prefix: str = "") -> list[str]:
    out = []
    for k in (model.model_extra or {}):
        if not k.startswith("_"):
            out.append(f"{prefix}{k}")
    for name in type(model).model_fields:
        value = getattr(model, name)
        if isinstance(value, BaseModel):
            out.extend(_collect_unknown_keys(value, f"{prefix}{name}."))
    return out


def validate_config(raw: dict) -> list[str]:
    """Validate parsed config.json data against ToolkitConfig.

    Returns a list of unknown-key warnings (full dotted paths) for the
    caller to print. Raises ConfigValidationError with field-precise lines
    when the shape is invalid. Never mutates `raw` — callers keep using the
    original dict.
    """
    try:
        model = ToolkitConfig.model_validate(raw)
    except ValidationError as e:
        raise ConfigValidationError(_format_errors(e)) from e
    return _collect_unknown_keys(model)
