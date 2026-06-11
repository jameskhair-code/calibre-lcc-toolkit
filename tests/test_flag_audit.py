"""Contract tests for flag-write audit logging (v1.10 item 3).

mark_mqg_complete and clear_mqg_flag write one audit entry per book with
source="flag" and step="flag:<command>". Three reader contracts are
load-bearing:

  1. The calibration loader (load_audit_records) excludes flag entries —
     they carry no confidence.
  2. The regrade staleness selector (find_stale_books) filters on exact AI
     step names, so the "flag:" namespace keeps a flag write from making a
     book look freshly enriched.
  3. A flag write inside a regrade context picks up the regrade marker at
     the audit_log choke point — harmless, since contracts 1 and 2 exclude
     the entry on other fields.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from calibre_toolkit.db import CalibreDB
from calibre_toolkit.logging_config import audit_log, regrade_audit
from calibre_toolkit.commands.audit import load_audit_records
from calibre_toolkit.commands.regrade import find_stale_books


def _build_minimal_calibre_db(library_path: Path) -> None:
    library_path.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(library_path / "metadata.db"))
    conn.executescript(
        """
        CREATE TABLE books (
            id INTEGER PRIMARY KEY,
            title TEXT,
            sort TEXT,
            author_sort TEXT,
            pubdate TEXT
        );
        CREATE TABLE custom_columns (
            id INTEGER PRIMARY KEY,
            label TEXT,
            datatype TEXT
        );
        CREATE TABLE custom_column_7 (
            book INTEGER,
            value INTEGER,
            UNIQUE(book)
        );
        """
    )
    conn.executemany("INSERT INTO books (id, title) VALUES (?, ?)", [
        (1, "Book One"),
        (2, "Book Two"),
    ])
    conn.execute(
        "INSERT INTO custom_columns (id, label, datatype) VALUES (7, 'mqg_lcc_manual', 'bool')"
    )
    conn.commit()
    conn.close()


@pytest.fixture
def db(tmp_path: Path) -> CalibreDB:
    library = tmp_path / "lib"
    _build_minimal_calibre_db(library)
    return CalibreDB(library_path=str(library), calibredb_path="calibredb")


@pytest.fixture
def audit_path(tmp_path: Path) -> Path:
    # The conftest autouse fixture points CALIBRE_TOOLKIT_AUDIT_LOG here.
    return tmp_path / "audit.log"


def _entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ── Writer contract ──────────────────────────────────────────────────────────


def test_mark_writes_one_entry_per_book(db: CalibreDB, audit_path: Path):
    db.mark_mqg_complete([1, 2], "#mqg_lcc_manual", audit_step="lcc-enrich")
    entries = _entries(audit_path)
    assert len(entries) == 2
    assert {e["book_id"] for e in entries} == {1, 2}
    for e in entries:
        assert e["field"] == "#mqg_lcc_manual"
        assert e["new_value"] is True
        assert e["source"] == "flag"
        assert e["step"] == "flag:lcc-enrich"
        assert "confidence" not in e


def test_clear_writes_entry_with_null_value(db: CalibreDB, audit_path: Path):
    db.mark_mqg_complete([1], "#mqg_lcc_manual", audit_step="lcc-enrich")
    db.clear_mqg_flag(1, "#mqg_lcc_manual", audit_step="unflag-manual")
    entries = _entries(audit_path)
    assert len(entries) == 2
    clear = entries[-1]
    assert clear["book_id"] == 1
    assert clear["new_value"] is None
    assert clear["source"] == "flag"
    assert clear["step"] == "flag:unflag-manual"


def test_default_step_is_bare_flag(db: CalibreDB, audit_path: Path):
    db.mark_mqg_complete([1], "#mqg_lcc_manual")
    assert _entries(audit_path)[0]["step"] == "flag"


def test_mark_unknown_column_noop_writes_no_entry(db: CalibreDB, audit_path: Path):
    db.mark_mqg_complete([1], "#no_such_column", audit_step="lcc-enrich")
    assert _entries(audit_path) == []


def test_clear_unknown_column_raises_and_writes_no_entry(db: CalibreDB, audit_path: Path):
    with pytest.raises(RuntimeError, match="not found"):
        db.clear_mqg_flag(1, "#no_such_column", audit_step="unflag-manual")
    assert _entries(audit_path) == []


# ── Reader contract 1: calibration excludes flag entries ─────────────────────


def test_calibration_loader_excludes_flag_entries(db: CalibreDB, audit_path: Path):
    audit_log(1, "#lcc", "PR6059", confidence="high", source="ai", step="lcc-enrich")
    db.mark_mqg_complete([1], "#mqg_lcc_manual", audit_step="lcc-enrich")

    records = load_audit_records(audit_path)
    assert len(records) == 1
    assert records[0].field == "#lcc"
    assert records[0].source == "ai"


# ── Reader contract 2: regrade staleness ignores flag entries ────────────────


def test_flag_entry_does_not_refresh_regrade_staleness():
    entries = [
        {"timestamp": "2026-05-01T00:00:00+00:00", "book_id": 1,
         "field": "#lcc", "new_value": "PR6059",
         "confidence": "high", "source": "ai", "step": "lcc-enrich"},
        # Later flag write for the same book — must NOT make it look fresh.
        {"timestamp": "2026-06-09T00:00:00+00:00", "book_id": 1,
         "field": "#mqg_lcc", "new_value": True,
         "source": "flag", "step": "flag:lcc-enrich"},
    ]
    before = datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert find_stale_books(entries, "lcc-enrich", before) == [1]


# ── Reader contract 3: regrade marker rides along harmlessly ─────────────────


def test_flag_inside_regrade_context_carries_marker_and_stays_excluded(
    db: CalibreDB, audit_path: Path,
):
    with regrade_audit("2026-06-01"):
        db.mark_mqg_complete([1], "#mqg_lcc_manual", audit_step="lcc-enrich")
    entry = _entries(audit_path)[0]
    assert entry["regrade"] == "2026-06-01"
    assert load_audit_records(audit_path) == []
