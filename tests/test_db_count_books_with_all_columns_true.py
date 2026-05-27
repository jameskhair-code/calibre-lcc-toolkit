"""Tests for `CalibreDB.count_books_with_all_columns_true` (v1.6 item 4).

Builds a minimal Calibre-schema-compatible SQLite at a tempdir,
including the `custom_columns` registry and a few `custom_column_N`
tables, and exercises the AND-across-columns count.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from calibre_toolkit.db import CalibreDB


def _build_db(library_path: Path) -> None:
    """Minimal schema: books + custom_columns registry + three boolean
    custom column tables (ids 1, 2, 3 → labels mqg_a, mqg_b, mqg_c)."""
    library_path.mkdir(parents=True, exist_ok=True)
    db_path = library_path / "metadata.db"
    conn = sqlite3.connect(str(db_path))
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
            label TEXT NOT NULL,
            name TEXT,
            datatype TEXT,
            display TEXT,
            is_multiple INTEGER,
            normalized INTEGER
        );
        CREATE TABLE custom_column_1 (
            id INTEGER PRIMARY KEY,
            book INTEGER NOT NULL,
            value BOOL NOT NULL
        );
        CREATE TABLE custom_column_2 (
            id INTEGER PRIMARY KEY,
            book INTEGER NOT NULL,
            value BOOL NOT NULL
        );
        CREATE TABLE custom_column_3 (
            id INTEGER PRIMARY KEY,
            book INTEGER NOT NULL,
            value BOOL NOT NULL
        );
        """
    )

    # 5 books.
    conn.executemany("INSERT INTO books (id, title) VALUES (?, ?)", [
        (1, "Book One"), (2, "Book Two"), (3, "Book Three"),
        (4, "Book Four"), (5, "Book Five"),
    ])

    # Three boolean custom columns.
    conn.executemany(
        "INSERT INTO custom_columns (id, label, name, datatype, display, is_multiple, normalized) "
        "VALUES (?, ?, ?, 'bool', '{}', 0, 0)",
        [
            (1, "mqg_a", "MQG-A"),
            (2, "mqg_b", "MQG-B"),
            (3, "mqg_c", "MQG-C"),
        ],
    )

    # Distribution chosen so each AND-combination has a distinct count:
    #   A true: 1,2,3,4    B true: 1,2,3      C true: 1,2
    #   A∩B:    1,2,3      A∩B∩C: 1,2
    conn.executemany("INSERT INTO custom_column_1 (book, value) VALUES (?, 1)",
                     [(1,), (2,), (3,), (4,)])
    conn.executemany("INSERT INTO custom_column_2 (book, value) VALUES (?, 1)",
                     [(1,), (2,), (3,)])
    conn.executemany("INSERT INTO custom_column_3 (book, value) VALUES (?, 1)",
                     [(1,), (2,)])

    conn.commit()
    conn.close()


@pytest.fixture
def db(tmp_path: Path) -> CalibreDB:
    lib = tmp_path / "library"
    _build_db(lib)
    return CalibreDB(library_path=str(lib), calibredb_path="calibredb")


def test_single_column(db: CalibreDB) -> None:
    assert db.count_books_with_all_columns_true(["#mqg_a"]) == 4
    assert db.count_books_with_all_columns_true(["#mqg_b"]) == 3
    assert db.count_books_with_all_columns_true(["#mqg_c"]) == 2


def test_two_columns_intersect(db: CalibreDB) -> None:
    assert db.count_books_with_all_columns_true(["#mqg_a", "#mqg_b"]) == 3


def test_three_columns_intersect(db: CalibreDB) -> None:
    assert db.count_books_with_all_columns_true(["#mqg_a", "#mqg_b", "#mqg_c"]) == 2


def test_label_without_hash_prefix(db: CalibreDB) -> None:
    """count_column_true accepts labels with or without leading '#';
    the new method follows the same convention."""
    assert db.count_books_with_all_columns_true(["mqg_a", "mqg_b"]) == 3


def test_missing_column_returns_zero(db: CalibreDB) -> None:
    """A column that doesn't exist in the library means no book can be
    fully complete against the gate — return 0 rather than ignoring the
    column."""
    assert db.count_books_with_all_columns_true(["#mqg_a", "#mqg_does_not_exist"]) == 0


def test_empty_label_list(db: CalibreDB) -> None:
    assert db.count_books_with_all_columns_true([]) == 0
