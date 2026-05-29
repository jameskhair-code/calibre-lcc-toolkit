"""Re-grade workflow (v1.8 PR 6).

Hermetic — tmpdir audit logs, a fake DB, no Calibre/AI. Covers the stale-book
selector, the regrade audit marker (set at the audit_log choke point),
calibration exclusion, per-step manual-column resolution, and a dry-run pass
through run_regrade including the manual-flag skip.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    """Strip ANSI styling so assertions match Rich's interleaved output."""
    return _ANSI.sub("", text)

from calibre_toolkit.logging_config import audit_log, regrade_audit
from calibre_toolkit.commands.audit_log import read_audit_entries
from calibre_toolkit.commands.audit import load_audit_records
from calibre_toolkit.commands.regrade import (
    find_stale_books,
    run_regrade,
    _manual_column,
)


def _entry(bid, step="lcc-enrich", ts="2026-05-01T10:00:00+00:00",
           source="ai", conf="high", regrade=None):
    d = {"timestamp": ts, "book_id": bid, "field": "#lcc", "new_value": "x",
         "confidence": conf, "source": source, "step": step}
    if regrade:
        d["regrade"] = regrade
    return d


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


CUTOFF = datetime(2026, 5, 15, tzinfo=timezone.utc)


# ── find_stale_books ─────────────────────────────────────────────────────────


def test_selects_books_with_latest_entry_before_cutoff():
    entries = [
        _entry(100, ts="2026-05-01T10:00:00+00:00"),   # stale
        _entry(102, ts="2026-05-10T10:00:00+00:00"),   # stale
        _entry(103, ts="2026-05-18T10:00:00+00:00"),   # fresh (after cutoff)
    ]
    assert find_stale_books(entries, "lcc-enrich", CUTOFF) == [100, 102]


def test_already_regraded_book_drops_out():
    # Latest entry (the re-grade) is after the cutoff → not selected again.
    entries = [
        _entry(101, ts="2026-05-01T10:00:00+00:00"),
        _entry(101, ts="2026-05-20T10:00:00+00:00", regrade="2026-05-15"),
    ]
    assert find_stale_books(entries, "lcc-enrich", CUTOFF) == []


def test_selector_is_step_scoped():
    entries = [
        _entry(100, step="lcc-enrich", ts="2026-05-01T10:00:00+00:00"),
        _entry(200, step="comments-enrich", ts="2026-05-01T10:00:00+00:00"),
    ]
    assert find_stale_books(entries, "lcc-enrich", CUTOFF) == [100]
    assert find_stale_books(entries, "comments-enrich", CUTOFF) == [200]


def test_selector_skips_unparseable_timestamp_and_bad_id():
    entries = [
        _entry(100, ts="2026-05-01T10:00:00+00:00"),
        _entry(101, ts="garbage"),
        {"book_id": "oops", "step": "lcc-enrich", "timestamp": "2026-05-01T10:00:00+00:00"},
    ]
    assert find_stale_books(entries, "lcc-enrich", CUTOFF) == [100]


# ── regrade audit marker (choke point) ───────────────────────────────────────


def test_regrade_audit_marks_only_entries_in_scope(tmp_path, monkeypatch):
    p = tmp_path / "audit.log"
    monkeypatch.setenv("CALIBRE_TOOLKIT_AUDIT_LOG", str(p))

    audit_log(1, "comments", "a", confidence="high", source="ai", step="comments-enrich")
    with regrade_audit("2026-05-15"):
        audit_log(2, "comments", "b", confidence="high", source="ai", step="comments-enrich")
    audit_log(3, "comments", "c", confidence="high", source="ai", step="comments-enrich")

    by_id = {e["book_id"]: e for e in read_audit_entries(p)}
    assert "regrade" not in by_id[1]            # before scope
    assert by_id[2]["regrade"] == "2026-05-15"  # in scope
    assert "regrade" not in by_id[3]            # scope reset on exit


# ── calibration exclusion ────────────────────────────────────────────────────


def test_regrade_entries_excluded_from_calibration(tmp_path):
    p = tmp_path / "audit.log"
    _write(p, [
        _entry(1, step="lcc-enrich"),
        _entry(2, step="lcc-enrich", regrade="2026-05-15"),
    ])
    book_ids = {r.book_id for r in load_audit_records(p)}
    assert book_ids == {1}   # the re-grade entry (book 2) is excluded


# ── _manual_column (per-step config location) ────────────────────────────────


def test_manual_column_resolves_per_step():
    cfg = {
        "mqg":      {"lcc_manual_column": "#mqg_lcc_manual"},
        "comments": {"mqg_manual_column": "#mqg_comments_manual"},
        "tags":     {"mqg_manual_column": "#mqg_tags_manual"},
    }
    assert _manual_column(cfg, "lcc-enrich") == "#mqg_lcc_manual"
    assert _manual_column(cfg, "comments-enrich") == "#mqg_comments_manual"
    assert _manual_column(cfg, "tags-enrich") == "#mqg_tags_manual"


# ── run_regrade dry-run + manual-flag skip ───────────────────────────────────


class _FakeDB:
    """Only the surface run_regrade touches in dry-run: _search_ids."""
    def __init__(self, flagged=()):
        self._flagged = list(flagged)

    def _search_ids(self, query):
        return list(self._flagged)


def test_run_regrade_dry_run_skips_manual_flagged(tmp_path, capsys):
    p = tmp_path / "audit.log"
    _write(p, [
        _entry(100, ts="2026-05-01T10:00:00+00:00"),
        _entry(101, ts="2026-05-02T10:00:00+00:00"),  # this one is manually flagged
        _entry(102, ts="2026-05-03T10:00:00+00:00"),
    ])
    cfg = {"mqg": {"lcc_manual_column": "#mqg_lcc_manual"}}
    db = _FakeDB(flagged=[101])

    run_regrade(
        db, None, cfg,
        step="lcc-enrich", before=CUTOFF, before_label="2026-05-15",
        audit_path=p, dry_run=True, force=False, limit=None,
        apply_confirm_threshold=20,
    )
    out = _plain(capsys.readouterr().out)
    assert "2 book(s) stale" in out          # 101 excluded → 2 remain
    assert "Skipped 1 manually-curated" in out
    assert "Dry-run" in out


def test_run_regrade_force_includes_manual_flagged(tmp_path, capsys):
    p = tmp_path / "audit.log"
    _write(p, [
        _entry(100, ts="2026-05-01T10:00:00+00:00"),
        _entry(101, ts="2026-05-02T10:00:00+00:00"),
    ])
    cfg = {"mqg": {"lcc_manual_column": "#mqg_lcc_manual"}}
    db = _FakeDB(flagged=[101])

    run_regrade(
        db, None, cfg,
        step="lcc-enrich", before=CUTOFF, before_label="2026-05-15",
        audit_path=p, dry_run=True, force=True, limit=None,
        apply_confirm_threshold=20,
    )
    out = _plain(capsys.readouterr().out)
    assert "2 book(s) stale" in out          # --force keeps 101
    assert "manually-curated" not in out


def test_run_regrade_no_stale_books(tmp_path, capsys):
    p = tmp_path / "audit.log"
    _write(p, [_entry(100, ts="2026-06-01T10:00:00+00:00")])  # after cutoff
    run_regrade(
        _FakeDB(), None, {},
        step="lcc-enrich", before=CUTOFF, before_label="2026-05-15",
        audit_path=p, dry_run=True, force=False, limit=None,
        apply_confirm_threshold=20,
    )
    assert "No stale writes" in _plain(capsys.readouterr().out)
