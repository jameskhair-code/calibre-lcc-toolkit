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


@pytest.fixture(autouse=True)
def _isolated_audit_log(tmp_path: Path, monkeypatch):
    """Keep every test's audit trail out of ~/.calibre-toolkit/audit.log.

    Flag writes audit through db.mark_mqg_complete / clear_mqg_flag since
    v1.10, so any test touching those methods would otherwise append to the
    user's real audit log. Tests that need a specific path still win — their
    own monkeypatch.setenv overwrites this one.
    """
    monkeypatch.setenv("CALIBRE_TOOLKIT_AUDIT_LOG", str(tmp_path / "audit.log"))


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
