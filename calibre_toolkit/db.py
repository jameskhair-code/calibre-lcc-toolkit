"""
Direct read access to the Calibre SQLite database.
All writes go through calibredb CLI to avoid corrupting the DB while Calibre is open.
"""

import sqlite3
import subprocess
import json
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class BookDetails:
    """Extended metadata for a single book, used by the Comments module."""
    book_id: int
    tags: list[str] = field(default_factory=list)
    series: str = ""
    series_index: float | None = None
    publisher: str = ""
    pubdate: str = ""           # "YYYY" or empty
    existing_comments: str = "" # raw HTML from Calibre


@dataclass
class Book:
    id: int
    title: str
    authors: list[str]
    sort_title: str = ""
    author_sort: str = ""

    @property
    def authors_display(self) -> str:
        return " & ".join(self.authors)


class CalibreDB:
    def __init__(self, library_path: str, calibredb_path: str = "calibredb"):
        self.library_path = Path(library_path)
        self.calibredb_path = calibredb_path
        self._db_path = self.library_path / "metadata.db"
        if not self._db_path.exists():
            raise FileNotFoundError(
                f"Calibre database not found at {self._db_path}\n"
                "Check the library_path in your config.json."
            )

    def _connect(self) -> sqlite3.Connection:
        # Open read-only so we can't accidentally corrupt anything
        uri = f"file:{self._db_path}?mode=ro"
        return sqlite3.connect(uri, uri=True, check_same_thread=False)

    def count_books(self) -> int:
        """Return the total number of books in the library via direct SQLite."""
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]

    def search(self, search_query: str) -> list[Book]:
        """
        Return books matching a Calibre search string.

        The special query "all" reads IDs directly from SQLite, bypassing
        calibredb so that GUI restrictions and virtual-library filters have
        no effect.  All other queries go through calibredb search to honour
        the full Calibre search syntax.
        """
        ids = self._search_ids(search_query)
        if not ids:
            return []
        return self._fetch_books(ids)

    def _search_ids(self, query: str) -> list[int]:
        """Resolve a Calibre search string to a list of book IDs.

        "all" (case-insensitive) uses SQLite directly to guarantee every book
        is included regardless of any restriction saved in the GUI state.
        All other queries go through calibredb search.
        """
        if query.strip().lower() == "all":
            return self._all_ids_from_sqlite()

        cmd = [
            self.calibredb_path,
            "search",
            "--library-path", str(self.library_path),
            query,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode != 0:
            # calibredb returns non-zero when no results found — that's fine
            stderr = result.stderr.strip()
            if "Another calibre program" in stderr:
                raise RuntimeError(
                    "Calibre is currently open.\n\n"
                    "Please close the main Calibre application before running this tool, "
                    "then try again.\n\n"
                    "calibredb cannot write to the library while Calibre is running."
                )
            if stderr and "No books found" not in stderr:
                raise RuntimeError(f"calibredb search failed: {stderr}")
            return []
        raw = result.stdout.strip()
        if not raw:
            return []
        return [int(x) for x in raw.split(",") if x.strip().isdigit()]

    def _all_ids_from_sqlite(self) -> list[int]:
        """Return every book ID in the library, ordered by ID."""
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM books ORDER BY id").fetchall()
        return [row[0] for row in rows]

    def _fetch_books(self, ids: list[int]) -> list[Book]:
        placeholders = ",".join("?" * len(ids))
        query = f"""
            SELECT
                b.id,
                b.title,
                b.sort      AS sort_title,
                b.author_sort,
                GROUP_CONCAT(a.name, ' & ') AS authors
            FROM books b
            LEFT JOIN books_authors_link bal ON bal.book = b.id
            LEFT JOIN authors a              ON a.id = bal.author
            WHERE b.id IN ({placeholders})
            GROUP BY b.id
            ORDER BY b.id
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, ids).fetchall()

        books = []
        for row in rows:
            raw_authors = row["authors"] or ""
            # SQLite GROUP_CONCAT joins with ' & ', but authors are stored individually
            authors = [a.strip() for a in raw_authors.split(" & ") if a.strip()]
            books.append(Book(
                id=row["id"],
                title=row["title"] or "",
                sort_title=row["sort_title"] or "",
                author_sort=row["author_sort"] or "",
                authors=authors,
            ))
        return books

    def apply_metadata(self, book_id: int, title: str | None, authors: list[str] | None) -> None:
        """Write title and/or authors back to Calibre via calibredb set_metadata."""
        if title is None and authors is None:
            return

        cmd = [
            self.calibredb_path,
            "set_metadata",
            "--library-path", str(self.library_path),
            str(book_id),
        ]
        if title is not None:
            cmd += ["--field", f"title:{title}"]
        if authors is not None:
            author_str = " & ".join(authors)
            cmd += ["--field", f"authors:{author_str}"]

        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode != 0:
            raise RuntimeError(
                f"calibredb set_metadata failed for book {book_id}: {result.stderr.strip()}"
            )

    def mark_mqg_complete(self, book_ids: list[int], column: str) -> None:
        """Mark a list of books as complete for a given MQG column."""
        for book_id in book_ids:
            cmd = [
                self.calibredb_path,
                "set_metadata",
                "--library-path", str(self.library_path),
                str(book_id),
                "--field", f"{column}:true",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result.returncode != 0:
                print(f"Warning: could not mark book {book_id} as MQG complete: {result.stderr.strip()}")

    def clear_mqg_flag(self, book_id: int, column: str) -> None:
        """Clear (set to false) a custom boolean MQG column for a single book."""
        cmd = [
            self.calibredb_path,
            "set_metadata",
            "--library-path", str(self.library_path),
            str(book_id),
            "--field", f"{column}:false",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode != 0:
            raise RuntimeError(
                f"calibredb set_metadata failed for book {book_id}: {result.stderr.strip()}"
            )

    def get_identifiers(self, book_id: int) -> dict[str, str]:
        """Return {type: value} for all identifiers currently on a book."""
        query = "SELECT type, val FROM identifiers WHERE book = ?"
        with self._connect() as conn:
            rows = conn.execute(query, [book_id]).fetchall()
        return {row[0]: row[1] for row in rows}

    def get_custom_column_batch(self, book_ids: list[int], label: str) -> dict[int, str]:
        """Read a Calibre custom text column for many books at once.

        label is the column's lookup name with or without the leading '#'.
        Returns {book_id: value} only for books that have a non-empty value.
        Handles both inline (custom_column_N) and normalized (link-table) text columns.
        """
        if not book_ids:
            return {}
        label_clean = label.lstrip("#")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, normalized FROM custom_columns WHERE label = ?",
                [label_clean],
            ).fetchone()
            if row is None:
                return {}
            col_id, normalized = row[0], bool(row[1])
            placeholders = ",".join("?" * len(book_ids))
            if normalized:
                query = (
                    f"SELECT link.book, cc.value "
                    f"FROM books_custom_column_{col_id}_link link "
                    f"JOIN custom_column_{col_id} cc ON cc.id = link.value "
                    f"WHERE link.book IN ({placeholders})"
                )
            else:
                query = (
                    f"SELECT book, value FROM custom_column_{col_id} "
                    f"WHERE book IN ({placeholders})"
                )
            rows = conn.execute(query, book_ids).fetchall()
        return {row[0]: row[1] for row in rows if row[1]}

    def apply_custom_fields(self, book_id: int, fields: dict[str, str]) -> None:
        """Set multiple custom column values for a book in a single calibredb call.

        fields keys are lookup names with the leading '#'.
        Empty-string values are written as empty (clears the field).
        """
        if not fields:
            return
        cmd = [
            self.calibredb_path,
            "set_metadata",
            "--library-path", str(self.library_path),
            str(book_id),
        ]
        for label, value in fields.items():
            cmd += ["--field", f"{label}:{value}"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(
                f"calibredb set_metadata failed for book {book_id}: {result.stderr.strip()}"
            )

    def get_book_details_batch(self, book_ids: list[int]) -> dict[int, "BookDetails"]:
        """Return tags, series, publisher, pubdate, and existing comments for many books.

        Returns {book_id: BookDetails} for every requested ID (missing fields default
        to empty).  All reads go through the read-only SQLite connection.
        """
        if not book_ids:
            return {}
        ph = ",".join("?" * len(book_ids))
        details: dict[int, BookDetails] = {bid: BookDetails(book_id=bid) for bid in book_ids}

        with self._connect() as conn:
            # Tags
            for row in conn.execute(
                f"SELECT btl.book, t.name FROM books_tags_link btl "
                f"JOIN tags t ON t.id = btl.tag "
                f"WHERE btl.book IN ({ph}) ORDER BY btl.book, t.name",
                book_ids,
            ).fetchall():
                bid, tag = row
                if bid in details:
                    details[bid].tags.append(tag)

            # Series
            for row in conn.execute(
                f"SELECT bsl.book, s.name, b.series_index "
                f"FROM books_series_link bsl "
                f"JOIN series s ON s.id = bsl.series "
                f"JOIN books b ON b.id = bsl.book "
                f"WHERE bsl.book IN ({ph})",
                book_ids,
            ).fetchall():
                bid, sname, sidx = row
                if bid in details:
                    details[bid].series = sname or ""
                    try:
                        details[bid].series_index = float(sidx) if sidx is not None else None
                    except (TypeError, ValueError):
                        pass

            # Publisher
            for row in conn.execute(
                f"SELECT bpl.book, p.name "
                f"FROM books_publishers_link bpl "
                f"JOIN publishers p ON p.id = bpl.publisher "
                f"WHERE bpl.book IN ({ph})",
                book_ids,
            ).fetchall():
                bid, pname = row
                if bid in details:
                    details[bid].publisher = pname or ""

            # Publication year (stored as ISO datetime string)
            for row in conn.execute(
                f"SELECT id, pubdate FROM books WHERE id IN ({ph})",
                book_ids,
            ).fetchall():
                bid, pubdate_raw = row
                if bid in details and pubdate_raw:
                    year = str(pubdate_raw)[:4]
                    if year.isdigit() and int(year) > 1000:
                        details[bid].pubdate = year

            # Existing comments
            for row in conn.execute(
                f"SELECT book, text FROM comments WHERE book IN ({ph})",
                book_ids,
            ).fetchall():
                bid, ctext = row
                if bid in details and ctext:
                    details[bid].existing_comments = ctext

        return details

    def get_tags_batch(self, book_ids: list[int]) -> dict[int, list[str]]:
        """Return {book_id: [tag, ...]} for many books, sorted alphabetically."""
        if not book_ids:
            return {}
        ph = ",".join("?" * len(book_ids))
        result: dict[int, list[str]] = {bid: [] for bid in book_ids}
        with self._connect() as conn:
            for row in conn.execute(
                f"SELECT btl.book, t.name FROM books_tags_link btl "
                f"JOIN tags t ON t.id = btl.tag "
                f"WHERE btl.book IN ({ph}) ORDER BY btl.book, t.name",
                book_ids,
            ).fetchall():
                bid, tag = row
                if bid in result:
                    result[bid].append(tag)
        return result

    def get_all_tags(self) -> list[tuple[str, int]]:
        """Return [(tag_name, book_count), ...] for every tag in the library, count desc."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT t.name, COUNT(btl.book) AS cnt "
                "FROM tags t "
                "JOIN books_tags_link btl ON btl.tag = t.id "
                "GROUP BY t.id, t.name "
                "ORDER BY cnt DESC, t.name"
            ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def get_books_with_tag(self, tag_name: str) -> list[int]:
        """Return all book IDs that carry an exact-match tag (case-sensitive)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT btl.book FROM books_tags_link btl "
                "JOIN tags t ON t.id = btl.tag "
                "WHERE t.name = ?",
                [tag_name],
            ).fetchall()
        return [row[0] for row in rows]

    def apply_tags(self, book_id: int, tags: list[str]) -> None:
        """Replace all tags on a book via calibredb (comma-separated list)."""
        tags_str = ",".join(tags)
        cmd = [
            self.calibredb_path,
            "set_metadata",
            "--library-path", str(self.library_path),
            str(book_id),
            "--field", f"tags:{tags_str}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(
                f"calibredb set_metadata failed for book {book_id}: {result.stderr.strip()}"
            )

    def _connect_write(self) -> sqlite3.Connection:
        """Open a writable connection to the Calibre database.

        Only safe when Calibre's GUI is not running — direct writes bypass
        the in-memory cache. calibredb already refuses to run while Calibre
        is open, so by the time tag-cleanup reaches the apply phase the GUI
        is guaranteed closed.
        """
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def rename_tag(self, old_name: str, new_name: str) -> int:
        """Rename a tag library-wide in a single SQL operation.

        If new_name already exists, old_name's books are merged into it
        (duplicates on the same book are dropped). Returns the number of
        book-tag link rows that were changed.
        """
        with self._connect_write() as conn:
            old = conn.execute(
                "SELECT id FROM tags WHERE name = ?", [old_name]
            ).fetchone()
            if not old:
                return 0
            old_id = old[0]

            existing = conn.execute(
                "SELECT id FROM tags WHERE name = ?", [new_name]
            ).fetchone()

            if not existing:
                # Simple rename: no collision
                count = conn.execute(
                    "SELECT COUNT(*) FROM books_tags_link WHERE tag = ?", [old_id]
                ).fetchone()[0]
                conn.execute("UPDATE tags SET name = ? WHERE id = ?", [new_name, old_id])
            else:
                # Merge into existing target tag
                new_id = existing[0]
                count = conn.execute(
                    "SELECT COUNT(*) FROM books_tags_link WHERE tag = ?", [old_id]
                ).fetchone()[0]
                # Drop rows where the book already carries new_id (avoid UNIQUE violation)
                conn.execute(
                    "DELETE FROM books_tags_link WHERE tag = ? AND book IN "
                    "(SELECT book FROM books_tags_link WHERE tag = ?)",
                    [old_id, new_id],
                )
                # Re-point remaining rows to the target tag
                conn.execute(
                    "UPDATE books_tags_link SET tag = ? WHERE tag = ?",
                    [new_id, old_id],
                )
                conn.execute("DELETE FROM tags WHERE id = ?", [old_id])
            conn.commit()
        return count

    def drop_tag(self, name: str) -> int:
        """Remove a tag from all books library-wide. Returns affected link count."""
        with self._connect_write() as conn:
            row = conn.execute(
                "SELECT id FROM tags WHERE name = ?", [name]
            ).fetchone()
            if not row:
                return 0
            tag_id = row[0]
            count = conn.execute(
                "SELECT COUNT(*) FROM books_tags_link WHERE tag = ?", [tag_id]
            ).fetchone()[0]
            conn.execute("DELETE FROM books_tags_link WHERE tag = ?", [tag_id])
            conn.execute("DELETE FROM tags WHERE id = ?", [tag_id])
            conn.commit()
        return count

    def apply_comments(self, book_id: int, comments_html: str) -> None:
        """Write the native Calibre comments/description field via calibredb."""
        cmd = [
            self.calibredb_path,
            "set_metadata",
            "--library-path", str(self.library_path),
            str(book_id),
            "--field", f"comments:{comments_html}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(
                f"calibredb set_metadata failed for book {book_id}: {result.stderr.strip()}"
            )

    def apply_identifiers(self, book_id: int, merged: dict[str, str]) -> None:
        """Write a complete set of identifiers to Calibre via calibredb set_metadata.

        REPLACES all existing identifiers — caller must merge current + new before calling.
        Values containing ',' or ':' are skipped to avoid corrupting the field string.
        """
        safe = {
            k: v for k, v in merged.items()
            if v and "," not in v and k not in ("", "calibre")
        }
        id_str = ",".join(f"{k}:{v}" for k, v in safe.items())
        cmd = [
            self.calibredb_path,
            "set_metadata",
            "--library-path", str(self.library_path),
            str(book_id),
            "--field", f"identifiers:{id_str}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode != 0:
            raise RuntimeError(
                f"calibredb set_metadata failed for book {book_id}: {result.stderr.strip()}"
            )
