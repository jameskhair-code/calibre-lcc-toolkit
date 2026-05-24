"""Shared pytest fixtures.

Anything that requires network access — Anthropic, LC catalog, Open Library,
fetch-ebook-metadata — must be stubbed in the test, never live-called. The
fixtures in this file deliberately avoid touching the real Calibre database
or any external service so the suite is hermetic and CI-friendly.
"""

from __future__ import annotations

from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Absolute path to the per-suite fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def sample_books():
    """A short list of Book objects matching what db.search() would return."""
    from calibre_toolkit.db import Book
    return [
        Book(id=1, title="The Remains of the Day",
             authors=["Kazuo Ishiguro"], sort_title="Remains of the Day, The"),
        Book(id=2, title="Beloved",
             authors=["Toni Morrison"], sort_title="Beloved"),
        Book(id=3, title="Half of a Yellow Sun",
             authors=["Chimamanda Ngozi Adichie"]),
    ]
