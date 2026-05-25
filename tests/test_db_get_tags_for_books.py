"""Tests for `CalibreDB.get_tags_for_books` (roadmap item 18).

Builds a minimal Calibre-schema-compatible SQLite at a tempdir,
instantiates CalibreDB against it, and exercises the new helper.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from calibre_toolkit.db import CalibreDB


def _build_minimal_calibre_db(library_path: Path) -> None:
    """Create the smallest schema the helper needs: books, tags, books_tags_link."""
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
        CREATE TABLE tags (
            id INTEGER PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE books_tags_link (
            book INTEGER,
            tag INTEGER
        );
        """
    )
    # Three books, four tags, varied link table:
    #   book 1: Fiction, Cold War
    #   book 2: Fiction, Cyberpunk
    #   book 3: Nonfiction
    conn.executemany("INSERT INTO books (id, title) VALUES (?, ?)", [
        (1, "Book One"),
        (2, "Book Two"),
        (3, "Book Three"),
    ])
    conn.executemany("INSERT INTO tags (id, name) VALUES (?, ?)", [
        (10, "Fiction"),
        (11, "Cold War"),
        (12, "Cyberpunk"),
        (13, "Nonfiction"),
    ])
    conn.executemany("INSERT INTO books_tags_link (book, tag) VALUES (?, ?)", [
        (1, 10), (1, 11),
        (2, 10), (2, 12),
        (3, 13),
    ])
    conn.commit()
    conn.close()


@pytest.fixture
def db(tmp_path: Path) -> CalibreDB:
    library = tmp_path / "lib"
    _build_minimal_calibre_db(library)
    return CalibreDB(library_path=str(library), calibredb_path="calibredb")


def test_returns_tags_for_single_book(db):
    assert db.get_tags_for_books([1]) == {"Fiction", "Cold War"}


def test_returns_union_across_multiple_books(db):
    assert db.get_tags_for_books([1, 2]) == {"Fiction", "Cold War", "Cyberpunk"}


def test_empty_input_returns_empty_set(db):
    assert db.get_tags_for_books([]) == set()


def test_unknown_book_id_returns_empty_set(db):
    assert db.get_tags_for_books([99999]) == set()


def test_partial_known_id_returns_only_real_tags(db):
    assert db.get_tags_for_books([1, 99999]) == {"Fiction", "Cold War"}


def test_book_without_tags_returns_empty_when_alone(db, tmp_path):
    # Add a 4th book with no link rows.
    db_path = Path(db.library_path) / "metadata.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO books (id, title) VALUES (4, 'No Tags')")
    conn.commit()
    conn.close()
    assert db.get_tags_for_books([4]) == set()


def test_returns_full_library_tags_when_all_books_in_scope(db):
    # Union across all books should produce the full vocabulary.
    assert db.get_tags_for_books([1, 2, 3]) == {
        "Fiction", "Cold War", "Cyberpunk", "Nonfiction",
    }
