"""Retry behaviour for IdentifierFetcher._run.

The underlying fetch-ebook-metadata subprocess is fully stubbed via
monkeypatch on subprocess.run so the suite is hermetic.
"""

from __future__ import annotations

import subprocess

import pytest

from calibre_toolkit import fetcher as fetcher_mod
from calibre_toolkit import retry as retry_mod
from calibre_toolkit.fetcher import IdentifierFetcher


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(retry_mod.time, "sleep", lambda _s: None)


def _opf_xml(isbn: str = "9780571258246") -> str:
    return (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" '
        'xmlns:opf="http://www.idpf.org/2007/opf">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:title>Sample</dc:title>'
        '<dc:creator>Author A</dc:creator>'
        f'<dc:identifier opf:scheme="ISBN">{isbn}</dc:identifier>'
        '</metadata></package>'
    )


def test_timeout_retried_until_success(monkeypatch):
    attempts = {"n": 0}

    def fake_run(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=1)
        return subprocess.CompletedProcess(args[0], 0, stdout=_opf_xml(), stderr="")

    monkeypatch.setattr(fetcher_mod.subprocess, "run", fake_run)
    f = IdentifierFetcher(fetch_path="fake-bin", timeout=1, max_retries=5)
    result = f.fetch(isbn="9780571258246")
    assert result.error is None
    assert result.identifiers.get("isbn") == "9780571258246"
    assert attempts["n"] == 3


def test_timeout_after_exhaustion_surfaces_timeout_error(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=1)

    monkeypatch.setattr(fetcher_mod.subprocess, "run", fake_run)
    f = IdentifierFetcher(fetch_path="fake-bin", timeout=1, max_retries=2)
    result = f.fetch(isbn="9780571258246")
    assert result.error == "timeout"


def test_missing_binary_not_retried(monkeypatch):
    attempts = {"n": 0}

    def fake_run(*args, **kwargs):
        attempts["n"] += 1
        raise FileNotFoundError(2, "no such file")

    monkeypatch.setattr(fetcher_mod.subprocess, "run", fake_run)
    f = IdentifierFetcher(fetch_path="fake-bin", timeout=1, max_retries=5)
    result = f.fetch(isbn="9780571258246")
    assert result.error == "binary_not_found"
    assert attempts["n"] == 1


def test_no_results_not_retried(monkeypatch):
    attempts = {"n": 0}

    def fake_run(*args, **kwargs):
        attempts["n"] += 1
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="ISBN not found")

    monkeypatch.setattr(fetcher_mod.subprocess, "run", fake_run)
    f = IdentifierFetcher(fetch_path="fake-bin", timeout=1, max_retries=5)
    result = f.fetch(isbn="9780571258246")
    assert result.error is not None and result.error.startswith("no_results")
    assert attempts["n"] == 1


def test_transient_network_stderr_retried(monkeypatch):
    """When stderr mentions network/timeout, treat as transient and retry."""
    attempts = {"n": 0}

    def fake_run(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] < 2:
            return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="network connection reset")
        return subprocess.CompletedProcess(args[0], 0, stdout=_opf_xml(), stderr="")

    monkeypatch.setattr(fetcher_mod.subprocess, "run", fake_run)
    f = IdentifierFetcher(fetch_path="fake-bin", timeout=1, max_retries=3)
    result = f.fetch(isbn="9780571258246")
    assert result.error is None
    assert attempts["n"] == 2
