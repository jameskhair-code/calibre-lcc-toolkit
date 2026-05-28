"""Unit tests for the audit-confidence command (roadmap item 17).

Hermetic — no live DB, no Calibre, no AI calls. All paths are tempdir
and the interactive entry point is exercised separately by mocking
Rich's Prompt.ask.
"""

from __future__ import annotations

import inspect
import json
import random
from pathlib import Path

import pytest

from calibre_toolkit.commands.audit import (
    AuditRecord,
    Rating,
    compute_precision,
    flag_below_threshold,
    grading_order,
    load_audit_records,
    persist_session,
    run_audit_confidence,
    stratified_sample,
    _values_diverge,
    _truncate,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def _rec(book_id: int, step: str, confidence: str, field: str = "comments") -> dict:
    return {
        "timestamp": "2026-05-25T12:00:00+00:00",
        "book_id": book_id,
        "field": field,
        "new_value": f"value-{book_id}",
        "confidence": confidence,
        "source": "ai",
        "step": step,
    }


# ── load_audit_records ───────────────────────────────────────────────────────


def test_load_audit_records_returns_empty_when_path_missing(tmp_path: Path):
    assert load_audit_records(tmp_path / "missing.log") == []


def test_load_audit_records_parses_valid_jsonl(tmp_path: Path):
    p = tmp_path / "audit.log"
    _write_jsonl(p, [
        _rec(1, "comments-enrich", "high"),
        _rec(2, "tags-enrich", "medium"),
    ])
    recs = load_audit_records(p)
    assert len(recs) == 2
    assert recs[0].book_id == 1
    assert recs[0].step == "comments-enrich"
    assert recs[0].confidence == "high"


def test_load_audit_records_skips_malformed_lines(tmp_path: Path):
    p = tmp_path / "audit.log"
    p.write_text(
        json.dumps(_rec(1, "comments-enrich", "high")) + "\n"
        + "not-valid-json\n"
        + json.dumps(_rec(2, "tags-enrich", "low")) + "\n",
        encoding="utf-8",
    )
    recs = load_audit_records(p)
    # Malformed middle line is skipped; the two valid ones remain.
    assert len(recs) == 2


def test_load_audit_records_excludes_records_without_confidence(tmp_path: Path):
    # Manual mark_mqg_complete writes have no confidence/source — they
    # should not appear in the calibration pool.
    rec_no_conf = {
        "timestamp": "2026-05-25T12:00:00+00:00",
        "book_id": 99,
        "field": "#mqg_comments",
        "new_value": True,
    }
    p = tmp_path / "audit.log"
    _write_jsonl(p, [rec_no_conf, _rec(1, "comments-enrich", "high")])
    recs = load_audit_records(p)
    assert len(recs) == 1
    assert recs[0].book_id == 1


def test_load_audit_records_preserves_extra_fields(tmp_path: Path):
    p = tmp_path / "audit.log"
    rec = _rec(1, "comments-enrich", "high")
    rec["must_read_score"] = 8
    _write_jsonl(p, [rec])
    recs = load_audit_records(p)
    assert recs[0].extra == {"must_read_score": 8}


# ── stratified_sample ────────────────────────────────────────────────────────


def test_stratified_sample_groups_by_step_and_tier():
    records = [
        AuditRecord("t", i, "f", "v", "high", "ai", "comments-enrich")
        for i in range(1, 6)
    ] + [
        AuditRecord("t", i, "f", "v", "medium", "ai", "comments-enrich")
        for i in range(10, 13)
    ]
    sampled = stratified_sample(records, sample_size=10, rng=random.Random(42))
    assert ("comments-enrich", "high") in sampled
    assert ("comments-enrich", "medium") in sampled
    assert len(sampled[("comments-enrich", "high")]) == 5
    assert len(sampled[("comments-enrich", "medium")]) == 3


def test_stratified_sample_caps_at_sample_size():
    records = [
        AuditRecord("t", i, "f", "v", "high", "ai", "comments-enrich")
        for i in range(100)
    ]
    sampled = stratified_sample(records, sample_size=20, rng=random.Random(42))
    assert len(sampled[("comments-enrich", "high")]) == 20


def test_stratified_sample_is_deterministic_with_seed():
    records = [
        AuditRecord("t", i, "f", "v", "high", "ai", "comments-enrich")
        for i in range(50)
    ]
    s1 = stratified_sample(records, 5, rng=random.Random(123))
    s2 = stratified_sample(records, 5, rng=random.Random(123))
    ids1 = [r.book_id for r in s1[("comments-enrich", "high")]]
    ids2 = [r.book_id for r in s2[("comments-enrich", "high")]]
    assert ids1 == ids2


def test_stratified_sample_respects_step_filter():
    records = [
        AuditRecord("t", 1, "f", "v", "high", "ai", "comments-enrich"),
        AuditRecord("t", 2, "f", "v", "high", "ai", "tags-enrich"),
        AuditRecord("t", 3, "f", "v", "high", "ai", "lcc-enrich"),
    ]
    sampled = stratified_sample(records, 10, steps_filter=["tags-enrich"])
    assert list(sampled.keys()) == [("tags-enrich", "high")]


# ── grading_order ────────────────────────────────────────────────────────────


def _ar(book_id: int, step: str, tier: str) -> AuditRecord:
    return AuditRecord("t", book_id, "f", "v", tier, "ai", step)


def test_grading_order_high_tier_first_then_step():
    sampled = {
        ("tags-enrich", "low"):        [_ar(1, "tags-enrich", "low")],
        ("comments-enrich", "high"):   [_ar(2, "comments-enrich", "high")],
        ("tags-enrich", "high"):       [_ar(3, "tags-enrich", "high")],
        ("comments-enrich", "medium"): [_ar(4, "comments-enrich", "medium")],
    }
    order = grading_order(sampled)
    keys = [key for key, _ in order]
    # high tiers first (step alphabetical within tier), then medium, then low.
    assert keys == [
        ("comments-enrich", "high"),
        ("tags-enrich", "high"),
        ("comments-enrich", "medium"),
        ("tags-enrich", "low"),
    ]


def test_grading_order_unknown_tier_sorts_last():
    sampled = {
        ("comments-enrich", "weird"): [_ar(1, "comments-enrich", "weird")],
        ("comments-enrich", "high"):  [_ar(2, "comments-enrich", "high")],
    }
    keys = [key for key, _ in grading_order(sampled)]
    assert keys == [("comments-enrich", "high"), ("comments-enrich", "weird")]


def test_grading_order_preserves_within_group_order():
    recs = [_ar(i, "comments-enrich", "high") for i in (5, 3, 9)]
    sampled = {("comments-enrich", "high"): recs}
    order = grading_order(sampled)
    assert [rec.book_id for _, rec in order] == [5, 3, 9]


def test_default_sample_size_is_five():
    # First-run friction reduction: the default per-group sample dropped
    # from 20 to 5 (v1.8 item 2).
    assert inspect.signature(run_audit_confidence).parameters["sample_size"].default == 5


# ── compute_precision ────────────────────────────────────────────────────────


def _make_rating(step: str, tier: str, rating: str) -> Rating:
    rec = AuditRecord("t", 1, "f", "v", tier, "ai", step)
    return Rating(record=rec, current_value="v", rating=rating)


def test_compute_precision_strict_and_lenient():
    ratings = [
        _make_rating("comments-enrich", "high", "correct"),
        _make_rating("comments-enrich", "high", "correct"),
        _make_rating("comments-enrich", "high", "minor"),
        _make_rating("comments-enrich", "high", "wrong"),
    ]
    table = compute_precision(ratings)
    v = table[("comments-enrich", "high")]
    assert v["total"] == 4
    assert v["correct"] == 2
    assert v["minor"] == 1
    assert v["wrong"] == 1
    assert v["strict_precision"] == 0.5
    assert v["lenient_precision"] == 0.75


def test_compute_precision_skips_skipped_ratings():
    ratings = [
        _make_rating("comments-enrich", "high", "correct"),
        _make_rating("comments-enrich", "high", "skipped"),
        _make_rating("comments-enrich", "high", "skipped"),
    ]
    table = compute_precision(ratings)
    v = table[("comments-enrich", "high")]
    assert v["total"] == 1
    assert v["strict_precision"] == 1.0


def test_compute_precision_handles_all_skipped():
    ratings = [_make_rating("tags-enrich", "low", "skipped")]
    table = compute_precision(ratings)
    assert table == {}


def test_compute_precision_separates_step_and_tier():
    ratings = [
        _make_rating("comments-enrich", "high", "correct"),
        _make_rating("tags-enrich",     "high", "wrong"),
    ]
    table = compute_precision(ratings)
    assert table[("comments-enrich", "high")]["strict_precision"] == 1.0
    assert table[("tags-enrich",     "high")]["strict_precision"] == 0.0


# ── flag_below_threshold ─────────────────────────────────────────────────────


def test_flag_below_threshold_returns_low_precision_groups():
    table = {
        ("comments-enrich", "high"):   {"strict_precision": 0.9, "total": 10},
        ("comments-enrich", "medium"): {"strict_precision": 0.6, "total": 10},
        ("tags-enrich",     "low"):    {"strict_precision": 0.5, "total": 10},
    }
    flagged = flag_below_threshold(table, threshold=0.7)
    assert flagged == [("comments-enrich", "medium"), ("tags-enrich", "low")]


def test_flag_below_threshold_excludes_exactly_at_threshold():
    # Threshold is a floor — a tier at exactly 0.7 is acceptable.
    table = {("comments-enrich", "high"): {"strict_precision": 0.7, "total": 10}}
    assert flag_below_threshold(table, threshold=0.7) == []


# ── persist_session ──────────────────────────────────────────────────────────


def test_persist_session_appends_jsonl(tmp_path: Path):
    out = tmp_path / "calibration.jsonl"
    ratings = [
        Rating(
            record=AuditRecord("t", 1, "comments", "v", "high", "ai", "comments-enrich"),
            current_value="v",
            rating="correct",
        )
    ]
    table = {("comments-enrich", "high"): {
        "total": 1, "correct": 1, "minor": 0, "wrong": 0,
        "strict_precision": 1.0, "lenient_precision": 1.0,
    }}
    persist_session(out, "sess1", 0.7, ratings, table, flagged=[])
    persist_session(out, "sess2", 0.7, ratings, table, flagged=[])

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    d1 = json.loads(lines[0])
    d2 = json.loads(lines[1])
    assert d1["session_id"] == "sess1"
    assert d2["session_id"] == "sess2"
    assert d1["ratings"][0]["book_id"] == 1
    assert d1["precision_table"] == {"comments-enrich|high": {
        "total": 1, "correct": 1, "minor": 0, "wrong": 0,
        "strict_precision": 1.0, "lenient_precision": 1.0,
    }}


def test_persist_session_creates_parent_directory(tmp_path: Path):
    out = tmp_path / "nested" / "deeper" / "calibration.jsonl"
    persist_session(out, "s", 0.7, [], {}, flagged=[])
    assert out.exists()


# ── display helpers ──────────────────────────────────────────────────────────


def test_values_diverge_set_equality_for_lists():
    # Tag list order is not meaningful.
    assert not _values_diverge(["A", "B"], ["B", "A"])
    assert _values_diverge(["A", "B"], ["A", "C"])


def test_values_diverge_ignores_trailing_whitespace_for_strings():
    assert not _values_diverge("hello", "hello  ")
    assert _values_diverge("hello", "goodbye")


def test_values_diverge_handles_none_current():
    assert _values_diverge("anything", None)


def test_truncate_strips_html():
    out = _truncate("<h3>Header</h3><p>Body text here.</p>", max_chars=200)
    assert "<" not in out and ">" not in out
    assert "Header" in out and "Body text here" in out


def test_truncate_caps_long_strings():
    long = "x" * 500
    out = _truncate(long, max_chars=50)
    assert len(out) <= 51  # 50 + ellipsis
    assert out.endswith("…")


def test_truncate_renders_lists_as_csv():
    assert _truncate(["A", "B", "C"]) == "A, B, C"


def test_truncate_handles_none():
    assert _truncate(None) == "(no value)"
