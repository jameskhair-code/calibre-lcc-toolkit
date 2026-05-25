"""Cross-step context plumbing (roadmap item 16).

Verifies the comments excerpt is threaded into the tags prompt, and
that current tags are still passed to the comments prompt (regression).
"""

from __future__ import annotations

import json

from calibre_toolkit.ai import (
    _build_tags_user_message,
    _build_comments_user_message,
)
from calibre_toolkit.db import Book, BookDetails


def _book(book_id: int = 1, title: str = "Test", authors=None) -> Book:
    return Book(id=book_id, title=title, authors=authors or ["Author"])


# ── Tags prompt: comments excerpt threading ──────────────────────────────────

def test_tags_user_message_includes_comments_excerpt_when_provided():
    books = [_book(1)]
    tags_map = {1: ["Fiction"]}
    context_map: dict[int, dict[str, str]] = {1: {}}
    comments_excerpt_map = {1: "A vivid account of the Cold War years."}

    raw = _build_tags_user_message(books, tags_map, context_map, comments_excerpt_map)
    payload = json.loads(raw)

    assert payload[0]["existing_comments_excerpt"] == (
        "A vivid account of the Cold War years."
    )


def test_tags_user_message_omits_excerpt_when_empty_string():
    books = [_book(1)]
    tags_map = {1: []}
    context_map: dict[int, dict[str, str]] = {1: {}}
    comments_excerpt_map = {1: ""}  # explicit empty

    raw = _build_tags_user_message(books, tags_map, context_map, comments_excerpt_map)
    payload = json.loads(raw)

    assert "existing_comments_excerpt" not in payload[0]


def test_tags_user_message_omits_excerpt_when_map_is_none():
    books = [_book(1)]
    tags_map = {1: ["Fiction"]}
    context_map: dict[int, dict[str, str]] = {1: {}}

    raw = _build_tags_user_message(books, tags_map, context_map, None)
    payload = json.loads(raw)

    assert "existing_comments_excerpt" not in payload[0]


def test_tags_user_message_preserves_lcc_context_alongside_excerpt():
    books = [_book(1)]
    tags_map = {1: ["History"]}
    context_map = {
        1: {
            "lcc_primary_class": "D - World History",
            "lcc_secondary_class": "D843 - Cold War",
            "lcc_summary": "Cold War overview.",
        }
    }
    comments_excerpt_map = {1: "Cold War history of Berlin."}

    raw = _build_tags_user_message(books, tags_map, context_map, comments_excerpt_map)
    payload = json.loads(raw)

    item = payload[0]
    assert item["lcc_primary_class"] == "D - World History"
    assert item["lcc_secondary_class"] == "D843 - Cold War"
    assert item["lcc_summary"] == "Cold War overview."
    assert item["current_tags"] == ["History"]
    assert item["existing_comments_excerpt"] == "Cold War history of Berlin."


# ── Comments prompt: current tags still passed (regression) ──────────────────

def test_comments_user_message_still_includes_current_tags():
    """Tags were always part of the comments prompt — guard against regression
    while item 16 reshapes things around it."""
    books = [_book(1, title="Cold Mountain")]
    details_map = {
        1: BookDetails(
            book_id=1,
            tags=["Historical Fiction", "Civil War"],
            existing_comments="",
        )
    }
    raw = _build_comments_user_message(books, details_map, None)
    payload = json.loads(raw)
    assert payload[0]["tags"] == ["Historical Fiction", "Civil War"]
