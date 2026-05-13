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

    def search(self, search_query: str) -> list[Book]:
        """
        Return books matching a Calibre search string.
        Uses calibredb search to honour the full Calibre search syntax,
        then fetches details via direct SQLite for speed.
        """
        ids = self._search_ids(search_query)
        if not ids:
            return []
        return self._fetch_books(ids)

    def _search_ids(self, query: str) -> list[int]:
        """Use calibredb to resolve the search string into book IDs."""
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
                console_warn = f"Warning: could not mark book {book_id} as MQG complete: {result.stderr.strip()}"
                print(console_warn)
