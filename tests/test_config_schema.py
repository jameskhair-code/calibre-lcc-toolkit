"""Tests for the typed config validator (v1.9 item 6).

The contract: config.example.json validates forever (doc-drift guard);
errors are field-precise; `_`-prefixed keys are the comment convention and
stay silent; other unknown keys warn; credentials never echo in error
output; and the loader's dict passes through untouched (behaviour-identity).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from calibre_toolkit.config_schema import (
    ConfigValidationError,
    validate_config,
)

_REPO_ROOT = Path(__file__).parent.parent


def _example() -> dict:
    return json.loads((_REPO_ROOT / "config.example.json").read_text(encoding="utf-8"))


# ── The example config is a fixture ──────────────────────────────────────────

def test_example_config_validates_with_no_warnings():
    warnings = validate_config(_example())
    assert warnings == []


def test_minimal_config_validates():
    assert validate_config({"library_path": "/some/library"}) == []


# ── Field-precise errors ─────────────────────────────────────────────────────

def test_missing_library_path_is_field_precise():
    with pytest.raises(ConfigValidationError) as exc:
        validate_config({"calibredb_path": "calibredb"})
    assert any("library_path" in line and "required" in line.lower()
               for line in exc.value.errors)


def test_wrong_type_names_the_dotted_path():
    cfg = _example()
    cfg["review"]["apply_confirm_threshold"] = "twenty"
    with pytest.raises(ConfigValidationError) as exc:
        validate_config(cfg)
    assert any(line.startswith("review.apply_confirm_threshold:")
               for line in exc.value.errors)
    assert any("'twenty'" in line for line in exc.value.errors)


def test_wrong_type_in_nested_ai_override():
    cfg = _example()
    cfg["ai"]["lcc"]["model"] = 123
    with pytest.raises(ConfigValidationError) as exc:
        validate_config(cfg)
    assert any(line.startswith("ai.lcc.model:") for line in exc.value.errors)


def test_credential_values_never_echo_in_errors():
    cfg = _example()
    cfg["ai"]["api_key"] = 12345  # wrong type; the value must not be echoed
    with pytest.raises(ConfigValidationError) as exc:
        validate_config(cfg)
    line = next(l for l in exc.value.errors if l.startswith("ai.api_key:"))
    assert "12345" not in line


# ── Unknown-key policy ───────────────────────────────────────────────────────

def test_underscore_keys_are_silently_ignored():
    cfg = {"library_path": "/lib", "_comment": "x",
           "lcc": {"_comment": "y", "lcc_column": "#lcc"}}
    assert validate_config(cfg) == []


def test_unknown_top_level_key_warns_with_path():
    cfg = {"library_path": "/lib", "identifers": {"max_workers": 4}}
    assert validate_config(cfg) == ["identifers"]


def test_unknown_nested_key_warns_with_dotted_path():
    cfg = {"library_path": "/lib", "ai": {"modle": "latest"}}
    assert validate_config(cfg) == ["ai.modle"]


# ── Behaviour identity ───────────────────────────────────────────────────────

def test_validation_never_mutates_the_input_dict():
    cfg = _example()
    cfg["identifers_typo"] = {"x": 1}  # unknown key, still untouched
    before = copy.deepcopy(cfg)
    validate_config(cfg)
    assert cfg == before


def test_loader_returns_the_original_parsed_dict(tmp_path: Path, capsys):
    """_load_config returns json.load's dict verbatim — the validator is a
    typing layer, not a transformation."""
    from calibre_toolkit.commands._common import _load_config

    p = tmp_path / "config.json"
    raw = {"library_path": "/lib", "catalog": {"request_timeout_seconds": 30}}
    p.write_text(json.dumps(raw), encoding="utf-8")
    cfg = _load_config(p)
    assert cfg == raw  # no injected defaults, no dropped keys


def test_loader_exits_with_field_precise_panel_on_invalid(tmp_path: Path, capsys):
    import typer

    from calibre_toolkit.commands._common import _load_config

    p = tmp_path / "config.json"
    p.write_text(json.dumps({"review": {"apply_confirm_threshold": []}}), encoding="utf-8")
    with pytest.raises(typer.Exit):
        _load_config(p)
    out = capsys.readouterr().out
    assert "failed validation" in out
    assert "library_path" in out                       # missing required
    assert "review.apply_confirm_threshold" in out     # wrong type


def test_loader_exits_cleanly_on_broken_json(tmp_path: Path, capsys):
    import typer

    from calibre_toolkit.commands._common import _load_config

    p = tmp_path / "config.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(typer.Exit):
        _load_config(p)
    assert "not valid JSON" in capsys.readouterr().out
