"""Tests for the doctor state-file checks (v1.9 item 5).

The contract: absence is a normal note (ok), well-formed files report entry
counts (ok), corrupted lines are counted and flagged (warn) — and nothing
ever crashes on bad input, including binary garbage.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from calibre_toolkit.setup import (
    _check_jsonl_state_file,
    _check_state_files,
    _check_workkey_cache,
)


# ── JSONL state files ────────────────────────────────────────────────────────

def test_missing_jsonl_is_ok_with_note(tmp_path: Path):
    r = _check_jsonl_state_file("state: audit.log", tmp_path / "audit.log")
    assert r.status == "ok"
    assert "not created yet" in r.detail


def test_wellformed_jsonl_reports_entry_count(tmp_path: Path):
    p = tmp_path / "audit.log"
    p.write_text(
        '{"book_id": 1, "field": "tags"}\n'
        '{"book_id": 2, "field": "comments"}\n'
        "\n",  # blank lines are not entries and not malformed
        encoding="utf-8",
    )
    r = _check_jsonl_state_file("state: audit.log", p)
    assert r.status == "ok"
    assert "2 entries" in r.detail


def test_corrupted_lines_flagged_with_counts(tmp_path: Path):
    p = tmp_path / "audit.log"
    p.write_text(
        '{"book_id": 1}\n'
        "{truncated json\n"
        "not json at all\n"
        '{"book_id": 2}\n',
        encoding="utf-8",
    )
    r = _check_jsonl_state_file("state: audit.log", p)
    assert r.status == "warn"
    assert "2 of 4 line(s) malformed" in r.detail


def test_non_object_json_line_counts_as_malformed(tmp_path: Path):
    # The writer only emits objects; a bare array/string is corruption.
    p = tmp_path / "calibration.jsonl"
    p.write_text('{"session": "a"}\n[1, 2, 3]\n', encoding="utf-8")
    r = _check_jsonl_state_file("state: calibration.jsonl", p)
    assert r.status == "warn"
    assert "1 of 2 line(s) malformed" in r.detail


def test_binary_garbage_fails_without_crashing(tmp_path: Path):
    p = tmp_path / "audit.log"
    p.write_bytes(b"\xff\xfe\x00\x01\x80garbage")
    r = _check_jsonl_state_file("state: audit.log", p)
    assert r.status == "fail"
    assert "unreadable" in r.detail


# ── Work-key cache ───────────────────────────────────────────────────────────

@pytest.fixture
def cache_path(tmp_path: Path, monkeypatch):
    p = tmp_path / "ol-workkey-cache.json"
    monkeypatch.setenv("CALIBRE_TOOLKIT_OL_WORKKEY_CACHE", str(p))
    return p


def test_missing_cache_is_ok_with_note(cache_path: Path):
    r = _check_workkey_cache()
    assert r.status == "ok"
    assert "not created yet" in r.detail


def test_valid_cache_reports_entry_count(cache_path: Path):
    cache_path.write_text(json.dumps({
        "version": 1,
        "entries": {"isbn:1": {"k": "v"}, "isbn:2": {"k": "v"}},
    }), encoding="utf-8")
    r = _check_workkey_cache()
    assert r.status == "ok"
    assert "2 cached work-key entries" in r.detail


def test_corrupt_cache_warns_not_fails(cache_path: Path):
    cache_path.write_text("{not json", encoding="utf-8")
    r = _check_workkey_cache()
    assert r.status == "warn"
    assert "corrupt" in r.detail
    assert "rebuild" in r.detail


def test_wrong_schema_cache_warns(cache_path: Path):
    cache_path.write_text(json.dumps({"version": 99, "entries": {}}), encoding="utf-8")
    r = _check_workkey_cache()
    assert r.status == "warn"
    assert "unexpected schema" in r.detail


# ── Composition ──────────────────────────────────────────────────────────────

def test_check_state_files_covers_all_four(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CALIBRE_TOOLKIT_AUDIT_LOG", str(tmp_path / "audit.log"))
    monkeypatch.setenv("CALIBRE_TOOLKIT_OL_WORKKEY_CACHE", str(tmp_path / "cache.json"))
    results = _check_state_files()
    names = [r.name for r in results]
    assert names == [
        "state: audit.log",
        "state: calibration.jsonl",
        "state: rule-revisions.jsonl",
        "state: ol-workkey-cache.json",
    ]
    # Fresh-install shape: nothing exists, nothing fails. The calibration /
    # rule-revisions paths are the real home-dir defaults, so on a machine
    # with real state they are ok-with-count; either way, never warn/fail
    # purely from this hermetic setup for the env-overridden pair.
    assert results[0].status == "ok"
    assert results[3].status == "ok"
