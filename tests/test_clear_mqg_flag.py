"""Regression test for the unflag-manual re-queue bug.

Calibre's bool-column search treats `#col:true` as "column is defined" —
a 0-value row matches it. `clear_mqg_flag` used to write value=0, so an
"unflagged" book still matched the steps' `not #<manual>:true` exclusion
and was never re-queued. The fix deletes the row; this locks that contract
at the SQLite layer (the search semantics themselves were verified against
a real library, 2026-06-09).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from calibre_toolkit.db import CalibreDB


def _build_minimal_calibre_db(library_path: Path) -> None:
    """Smallest schema the flag helpers need: books, custom_columns, one bool column."""
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


def _rows(db: CalibreDB) -> dict[int, int]:
    conn = sqlite3.connect(str(Path(db.library_path) / "metadata.db"))
    rows = dict(conn.execute("SELECT book, value FROM custom_column_7").fetchall())
    conn.close()
    return rows


def test_clear_removes_the_row_not_zeroes_it(db: CalibreDB):
    db.mark_mqg_complete([1, 2], "#mqg_lcc_manual")
    assert _rows(db) == {1: 1, 2: 1}

    db.clear_mqg_flag(1, "#mqg_lcc_manual")

    rows = _rows(db)
    assert 1 not in rows, (
        "cleared flag must be UNDEFINED (row deleted) — a 0-value row still "
        "matches Calibre's `#col:true` and the book is never re-queued"
    )
    assert rows == {2: 1}  # other books untouched


def test_flag_clear_reflag_roundtrip(db: CalibreDB):
    db.mark_mqg_complete([1], "#mqg_lcc_manual")
    db.clear_mqg_flag(1, "#mqg_lcc_manual")
    db.mark_mqg_complete([1], "#mqg_lcc_manual")
    assert _rows(db) == {1: 1}


def test_clear_unflagged_book_is_noop(db: CalibreDB):
    db.clear_mqg_flag(1, "#mqg_lcc_manual")
    assert _rows(db) == {}


def test_clear_unknown_column_raises(db: CalibreDB):
    with pytest.raises(RuntimeError, match="not found"):
        db.clear_mqg_flag(1, "#no_such_column")
