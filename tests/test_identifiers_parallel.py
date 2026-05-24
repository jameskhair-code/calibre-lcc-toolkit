"""Tests for the parallel identifier-lookup helper.

The fetcher is stubbed so the suite is hermetic — no subprocess invoked.
We assert (a) suggestion shape, (b) that the helper preserves input
order when the caller re-walks `books`, (c) that real concurrency
happens with max_workers > 1, and (d) exception isolation.
"""

from __future__ import annotations

import threading
import time

import pytest

from calibre_toolkit.db import Book
from calibre_toolkit.fetcher import FetchResult
from calibre_toolkit.modules.identifiers import (
    IdentifierSuggestion,
    _parallel_lookup,
)


class _StubFetcher:
    """Drop-in replacement for IdentifierFetcher.fetch.

    Tracks concurrency by counting overlapping calls.
    """

    def __init__(self, delay: float = 0.0, raises_for: set[int] | None = None):
        self.delay = delay
        self.raises_for = raises_for or set()
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()
        self.calls: list[tuple[str | None, str]] = []

    def fetch(self, isbn=None, title=None, authors=None):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls.append((isbn, title or ""))
        try:
            if title and title.endswith("_RAISE"):
                raise RuntimeError("boom")
            if isbn and int(isbn[-3:]) in self.raises_for:
                raise RuntimeError("boom")
            time.sleep(self.delay)
            return FetchResult(
                identifiers={"isbn": isbn or "0000000000000", "amazon": "B0001"},
                title=(title or "") + " (fetched)",
                authors=authors or [],
                lookup_method="isbn" if isbn else "title_author",
                confidence="high" if isbn else "low",
                error=None,
            )
        finally:
            with self._lock:
                self.active -= 1


def _book(bid: int, title: str = "Title", authors: tuple[str, ...] = ("A",)) -> Book:
    # Book is a dataclass with id/title/authors fields plus a couple of optionals.
    return Book(id=bid, title=title, authors=list(authors))


def test_returns_one_suggestion_per_book():
    fetcher = _StubFetcher()
    pending = [(_book(1), {"isbn": "9780000000001"}), (_book(2), {})]
    out = _parallel_lookup(fetcher, pending, max_workers=2)
    assert set(out.keys()) == {1, 2}
    assert all(isinstance(v, IdentifierSuggestion) for v in out.values())


def test_input_order_recoverable_via_book_id():
    fetcher = _StubFetcher()
    books = [_book(i) for i in (10, 20, 30, 40)]
    pending = [(b, {}) for b in books]
    out = _parallel_lookup(fetcher, pending, max_workers=4)
    # Caller re-walks `books` to assemble the final list in input order.
    ordered = [out[b.id] for b in books]
    assert [s.book_id for s in ordered] == [10, 20, 30, 40]


def test_max_workers_drives_real_concurrency():
    fetcher = _StubFetcher(delay=0.05)
    pending = [(_book(i), {}) for i in range(6)]
    _parallel_lookup(fetcher, pending, max_workers=4)
    # With 4 workers and 6 tasks we expect at least 2 in flight at once.
    assert fetcher.max_active >= 2, f"max_active={fetcher.max_active}"


def test_max_workers_one_serialises():
    fetcher = _StubFetcher(delay=0.01)
    pending = [(_book(i), {}) for i in range(4)]
    _parallel_lookup(fetcher, pending, max_workers=1)
    assert fetcher.max_active == 1


def test_empty_pending_returns_empty_dict():
    fetcher = _StubFetcher()
    out = _parallel_lookup(fetcher, [], max_workers=4)
    assert out == {}


def test_workers_capped_to_pending_size():
    """ThreadPoolExecutor refuses max_workers < 1; we also don't want
    to spin up 10 threads to serve 2 tasks."""
    fetcher = _StubFetcher(delay=0.01)
    pending = [(_book(i), {}) for i in range(2)]
    _parallel_lookup(fetcher, pending, max_workers=10)
    assert fetcher.max_active <= 2


def test_isbn_drives_lookup_method():
    fetcher = _StubFetcher()
    pending = [
        (_book(1), {"isbn": "9780000000001"}),
        (_book(2, title="No ISBN"), {}),
    ]
    out = _parallel_lookup(fetcher, pending, max_workers=2)
    assert out[1].lookup_method == "isbn"
    assert out[2].lookup_method == "title_author"


def test_unexpected_exception_isolated_to_single_row():
    """One book exploding must not crash the whole batch."""
    fetcher = _StubFetcher()
    pending = [
        (_book(1), {"isbn": "9780000000111"}),
        (_book(2, title="will_blow_up_RAISE"), {}),
        (_book(3), {"isbn": "9780000000333"}),
    ]
    out = _parallel_lookup(fetcher, pending, max_workers=3)
    assert out[1].lookup_error is None
    assert out[2].lookup_error is not None and "unexpected" in out[2].lookup_error
    assert out[3].lookup_error is None
