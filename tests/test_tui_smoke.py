"""Hermetic smoke tests for the Textual TUI (tui/app.py).

Drives CalibreToolkitApp through Textual's Pilot harness — mounts the app,
presses keys, and asserts the right screen state. No real Calibre library or
network: the DB is a stub returning fixed counts, and the cumulative-cost
read (usage.jsonl) is patched to an empty aggregate so the mount path is
deterministic regardless of the maintainer's real usage log.

pytest-asyncio is not a dependency, so each test wraps the async Pilot flow in
asyncio.run() rather than declaring `async def` test functions.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from calibre_toolkit.tui.app import CalibreToolkitApp
from calibre_toolkit.usage import UsageAggregate


class _StubDB:
    """Minimal stand-in for CalibreDB covering only what _load_stats calls."""

    def __init__(self, total: int = 100):
        self._total = total

    def count_books(self) -> int:
        return self._total

    def count_column_true(self, label: str) -> int:
        # Deterministic per-column count so pipeline icons exercise the
        # done==total / 0<done<total / done==0 branches.
        return {"#mqg_title_author": self._total, "#mqg_identifiers": 40}.get(label, 0)

    def count_books_with_all_columns_true(self, labels: list[str]) -> int:
        return 10


_CFG = {
    "library_path": r"C:\Some\Calibre\Library",
    "mqg": {
        "title_author_column": "#mqg_title_author",
        "identifiers_column": "#mqg_identifiers",
        "lcc_column": "#mqg_lcc",
    },
    "comments": {"mqg_column": "#mqg_comments"},
    "tags": {"reviewed_column": "#tags_reviewed"},
}


def _make_app() -> CalibreToolkitApp:
    return CalibreToolkitApp(
        cfg=_CFG, db=_StubDB(), config_path=Path("config.json")
    )


@pytest.fixture(autouse=True)
def _hermetic_usage(monkeypatch):
    """Keep _load_stats off the real usage.jsonl."""
    monkeypatch.setattr(
        "calibre_toolkit.usage.replay_usage_log", lambda *a, **k: UsageAggregate()
    )


def _run(coro_factory):
    """Run an async Pilot flow built by coro_factory(app) -> coroutine."""
    app = _make_app()

    async def _driver():
        async with app.run_test() as pilot:
            return await coro_factory(app, pilot)

    return asyncio.run(_driver())


def test_app_mounts_with_expected_menu():
    from textual.widgets import ListView

    def _assert(app):
        # 5 numbered MQG steps + Maintenance header + Tags Cleanup = 7 rows.
        assert len(app._menu) == 7
        steps = app._steps_only()
        assert [s.number for s in steps] == ["01", "02", "03", "04", "05", ""]
        assert [s.name for s in steps][:5] == [
            "Title & Author", "Identifiers", "LCC Classification",
            "Comments", "Tags",
        ]
        list_view = app.query_one("#step-list", ListView)
        assert len(list_view.children) == 7
        # Header static is present.
        app.query_one("#left-header")

    async def _flow(app, pilot):
        _assert(app)

    _run(_flow)


def test_digit_jump_selects_step():
    from textual.widgets import Static

    async def _flow(app, pilot):
        await pilot.press("3")
        await pilot.pause()
        assert app._selected_idx == 2  # "3" -> jump(2) -> LCC
        assert "Step 03" in str(app.query_one("#r-number", Static).render())
        assert "LCC Classification" in str(app.query_one("#r-name", Static).render())

    _run(_flow)


def test_jump_to_maintenance_and_tags_cleanup():
    from textual.widgets import Static

    async def _flow(app, pilot):
        await pilot.press("m")
        await pilot.pause()
        assert app._selected_idx == 5
        assert "Maintenance" in str(app.query_one("#r-name", Static).render())

        await pilot.press("t")
        await pilot.pause()
        assert app._selected_idx == 6
        assert "Tags Cleanup" in str(app.query_one("#r-name", Static).render())
        # Maintenance step has no number -> r-number is blank.
        assert str(app.query_one("#r-number", Static).render()) == ""

    _run(_flow)


def test_action_buttons_populate_for_selected_step():
    async def _flow(app, pilot):
        await pilot.press("1")  # Title & Author (4 actions)
        await pilot.pause()
        buttons = app.query(".action-btn")
        assert len(buttons) == 4
        assert len(app._action_map) == 4
        # Every rendered button id maps to a StepAction.
        for btn in buttons:
            assert btn.id in app._action_map

    _run(_flow)


def test_cursor_keys_navigate():
    async def _flow(app, pilot):
        await pilot.press("1")
        await pilot.pause()
        start = app._selected_idx
        await pilot.press("j")  # cursor_down
        await pilot.pause()
        assert app._selected_idx == start + 1
        await pilot.press("k")  # cursor_up
        await pilot.pause()
        assert app._selected_idx == start

    _run(_flow)


def test_stats_render_after_load():
    from textual.widgets import Static

    async def _flow(app, pilot):
        await app.workers.wait_for_complete()
        await pilot.pause()
        header = str(app.query_one("#left-header", Static).render())
        assert "Pipeline:" in header
        assert "100" in header  # total books from the stub
        assert "books" in app.sub_title

    _run(_flow)


def test_bindings_present():
    app = _make_app()
    keys = {b.key: b.action for b in app.BINDINGS}
    assert keys["q"] == "quit"
    assert keys["r"] == "refresh_stats"
    for digit, idx in [("1", 0), ("2", 1), ("3", 2), ("4", 3), ("5", 4)]:
        assert keys[digit] == f"jump({idx})"
    assert keys["m"] == "jump(5)"
    assert keys["t"] == "jump(6)"
