"""
One-off scanner: find titles that look like they end with a standalone
volume/part designation (no series-name parenthetical).

Run from the project root:
    python scan_volume_titles.py

Reads library_path from config.json. Output is grouped by pattern so it's
easy to scan visually and decide whether a T-SER rule needs to change.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path


# Patterns we want to catch — titles whose tail looks like a series position
# expressed as a standalone volume number (no parenthetical series name).
PATTERNS = {
    ", Volume N (numeric)":  re.compile(r",\s*Volume\s+\d+(\s+of\s+\d+)?\s*$", re.IGNORECASE),
    ", Vol N / Vol. N":      re.compile(r",\s*Vol\.?\s+\d+(\s+of\s+\d+)?\s*$", re.IGNORECASE),
    ", Part N":              re.compile(r",\s*Part\s+\d+(\s+of\s+\d+)?\s*$", re.IGNORECASE),
    ", Book N":              re.compile(r",\s*Book\s+\d+(\s+of\s+\d+)?\s*$", re.IGNORECASE),
    " - Volume/Vol/Part N":  re.compile(r"\s[-–—]\s*(Volume|Vol\.?|Part|Book)\s+\d+\s*$", re.IGNORECASE),
}


def main() -> None:
    cfg_path = Path(__file__).parent / "config.json"
    if not cfg_path.exists():
        sys.exit(f"config.json not found at {cfg_path}")

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    library_path = Path(cfg["library_path"])
    db_path = library_path / "metadata.db"
    if not db_path.exists():
        sys.exit(f"metadata.db not found at {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = conn.execute("SELECT id, title FROM books ORDER BY title").fetchall()
    conn.close()

    matches: dict[str, list[tuple[int, str]]] = {name: [] for name in PATTERNS}
    for book_id, title in rows:
        if not title:
            continue
        for name, pattern in PATTERNS.items():
            if pattern.search(title):
                matches[name].append((book_id, title))
                break  # one bucket per book

    total = sum(len(v) for v in matches.values())
    print(f"\nScanned {len(rows):,} books — {total} matches across {len(PATTERNS)} patterns.\n")

    for name, hits in matches.items():
        print(f"── {name}  ({len(hits)} hits) " + "─" * (60 - len(name)))
        if not hits:
            print("   (none)")
        else:
            for book_id, title in hits[:50]:
                print(f"  [{book_id:>6}]  {title}")
            if len(hits) > 50:
                print(f"  … and {len(hits) - 50} more")
        print()


if __name__ == "__main__":
    main()
