"""Item 11 — verify the pre-fetched description threads through to the
LCC user prompt that the AI receives."""

from __future__ import annotations

import json

from calibre_toolkit.ai import _build_lcc_user_message
from calibre_toolkit.db import Book
from calibre_toolkit.services.book_description import BookDescription


def _book(book_id: int, title: str) -> Book:
    return Book(id=book_id, title=title, authors=["Test Author"])


def test_lcc_user_message_omits_description_when_map_empty():
    payload = json.loads(_build_lcc_user_message([_book(1, "X")], {}, {}))
    assert payload == [{"id": 1, "title": "X", "authors": ["Test Author"]}]


def test_lcc_user_message_omits_description_when_book_has_no_entry():
    """Books absent from description_map should look identical to the pre-item-11
    behaviour — no `description` key, no `description_source` key."""
    desc_map = {99: BookDescription(text="other", source="Google Books", categories=[])}
    payload = json.loads(_build_lcc_user_message([_book(1, "X")], {}, desc_map))
    assert "description" not in payload[0]
    assert "description_source" not in payload[0]


def test_lcc_user_message_includes_description_when_present():
    desc = BookDescription(
        text="A biography of Robert Moses examining mid-20th-century New York.",
        source="Google Books",
        categories=["Biography", "History / United States / 20th Century"],
    )
    payload = json.loads(_build_lcc_user_message([_book(1, "Power Broker")], {}, {1: desc}))
    item = payload[0]
    assert item["description"].startswith("A biography of Robert Moses")
    assert item["description_source"] == "Google Books"
    assert "Biography" in item["description_categories"]


def test_lcc_user_message_skips_description_when_text_is_empty():
    """A `BookDescription` with empty text should not pollute the prompt."""
    desc = BookDescription(text="", source="Google Books", categories=["Should not appear"])
    payload = json.loads(_build_lcc_user_message([_book(1, "X")], {}, {1: desc}))
    assert "description" not in payload[0]
    assert "description_source" not in payload[0]
    assert "description_categories" not in payload[0]


def test_lcc_user_message_includes_description_alongside_current_fields():
    """When the book already has partial LCC values AND a description, both
    appear in the payload."""
    desc = BookDescription(text="Some description.", source="Open Library", categories=[])
    current_map = {1: {"lcc": "", "lcc_primary_class": "P - Language & Literature",
                       "lcc_secondary_class": "", "lcc_summary": ""}}
    payload = json.loads(_build_lcc_user_message([_book(1, "X")], current_map, {1: desc}))
    item = payload[0]
    assert item["current"]["lcc_primary_class"] == "P - Language & Literature"
    assert item["description"] == "Some description."
    assert item["description_source"] == "Open Library"
