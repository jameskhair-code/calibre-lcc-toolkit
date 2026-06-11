"""Budget guardrail (v1.10 item 4).

project_step_cost projects a batch's AI cost from per-step usage history
(when the sample is large enough) or a static conservative estimate, and
budget_guardrail prompts above usage.confirm_above_usd — declining exits
before any AI call. There is no dry-run bypass: dry-runs make real AI
calls, so the spend gate fires on them too (PR #76 review correction to
the charter's wording).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer

from calibre_toolkit.usage import (
    _GUARDRAIL_MIN_CALLS,
    CostProjection,
    project_step_cost,
    replay_usage_log,
)
from calibre_toolkit.commands._common import _confirm_above_usd, budget_guardrail


def _write_usage(path: Path, step: str, calls: int,
                 input_tokens: int = 1000, output_tokens: int = 100) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for _ in range(calls):
            f.write(json.dumps({
                "timestamp": "2026-06-01T00:00:00+00:00",
                "model": "claude-sonnet-4-6",
                "step": step,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            }) + "\n")


@pytest.fixture(autouse=True)
def _isolated_usage_log(tmp_path: Path, monkeypatch):
    """Projections in tests must never read the real ~/.calibre-toolkit/usage.jsonl."""
    monkeypatch.setenv("CALIBRE_TOOLKIT_USAGE_LOG", str(tmp_path / "usage.jsonl"))


# ── replay step filter ───────────────────────────────────────────────────────


def test_replay_filters_by_step(tmp_path: Path):
    p = tmp_path / "u.jsonl"
    _write_usage(p, "tags", 3)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"model": "m", "step": "lcc", "input_tokens": 7,
                            "output_tokens": 0}) + "\n")
    assert replay_usage_log(p, step="tags").call_count == 3
    assert replay_usage_log(p, step="lcc").total.input_tokens == 7
    assert replay_usage_log(p).call_count == 4


# ── project_step_cost ────────────────────────────────────────────────────────


def test_history_basis_when_sample_sufficient(tmp_path: Path):
    p = tmp_path / "u.jsonl"
    # 12 calls x (1000 in + 100 out) on the tags step (assumed batch 20).
    # At Haiku prices: per call (1000*1 + 100*5)/1e6 = $0.0015;
    # per book 0.0015/20; x 1000 books = $0.075.
    _write_usage(p, "tags", calls=12)
    proj = project_step_cost("tags", 1000, "claude-haiku-4-5", path=p)
    assert proj is not None
    assert "usage history" in proj.basis and "12 calls" in proj.basis
    assert proj.estimated_usd == pytest.approx(0.075)


def test_static_basis_when_history_thin(tmp_path: Path):
    p = tmp_path / "u.jsonl"
    _write_usage(p, "tags", calls=_GUARDRAIL_MIN_CALLS - 1)
    proj = project_step_cost("tags", 1000, "claude-haiku-4-5", path=p)
    assert proj is not None
    assert "static estimate" in proj.basis
    # Static tags per-book (150/80/120/250) at Haiku prices:
    # (150*1 + 80*5 + 120*1.25 + 250*0.10)/1e6 = $0.000725 x 1000 = $0.725
    assert proj.estimated_usd == pytest.approx(0.725)


def test_unknown_step_uses_static_default(tmp_path: Path):
    proj = project_step_cost("never-seen", 10, "claude-sonnet-4-6",
                             path=tmp_path / "missing.jsonl")
    assert proj is not None
    assert "static estimate" in proj.basis
    assert proj.estimated_usd > 0


def test_unpriced_model_returns_none(tmp_path: Path):
    p = tmp_path / "u.jsonl"
    _write_usage(p, "tags", calls=20)
    assert project_step_cost("tags", 1000, "mystery-model", path=p) is None


# ── budget_guardrail ─────────────────────────────────────────────────────────


def _patch_confirm(monkeypatch, answer: bool) -> list:
    calls: list = []

    def fake_confirm(prompt, *a, **k):
        calls.append(prompt)
        return answer

    monkeypatch.setattr(typer, "confirm", fake_confirm)
    return calls


def test_no_prompt_at_or_below_threshold(monkeypatch, tmp_path: Path):
    calls = _patch_confirm(monkeypatch, answer=False)
    # Empty history -> static estimate; 1 tags book is well under $1.
    budget_guardrail(usage_step="tags", n_books=1,
                     model="claude-sonnet-4-6", threshold=1.0)
    assert calls == []


def test_prompt_over_threshold_proceeds_on_yes(monkeypatch, tmp_path: Path):
    calls = _patch_confirm(monkeypatch, answer=True)
    budget_guardrail(usage_step="comments", n_books=5000,
                     model="claude-sonnet-4-6", threshold=1.0)
    assert len(calls) == 1
    assert "5000 books" in calls[0] and "static estimate" in calls[0]


def test_decline_exits_before_ai(monkeypatch, tmp_path: Path):
    _patch_confirm(monkeypatch, answer=False)
    with pytest.raises(typer.Exit):
        budget_guardrail(usage_step="comments", n_books=5000,
                         model="claude-sonnet-4-6", threshold=1.0)


def test_dry_runs_get_no_bypass(monkeypatch, tmp_path: Path):
    """Dry-runs make real AI calls, so the gate has no dry_run knob at all —
    the prompt fires for a dry-run exactly as for a live run."""
    import inspect
    assert "dry_run" not in inspect.signature(budget_guardrail).parameters
    calls = _patch_confirm(monkeypatch, answer=False)
    with pytest.raises(typer.Exit):
        budget_guardrail(usage_step="comments", n_books=5000,
                         model="claude-sonnet-4-6", threshold=1.0)
    assert len(calls) == 1


def test_unpriced_model_never_prompts(monkeypatch, tmp_path: Path):
    calls = _patch_confirm(monkeypatch, answer=False)
    budget_guardrail(usage_step="comments", n_books=5000,
                     model="mystery-model", threshold=1.0)
    assert calls == []


# ── config knob ──────────────────────────────────────────────────────────────


def test_confirm_above_usd_default_and_override():
    assert _confirm_above_usd({}) == 1.0
    assert _confirm_above_usd({"usage": {"confirm_above_usd": 5}}) == 5.0
