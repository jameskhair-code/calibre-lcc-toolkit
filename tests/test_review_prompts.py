"""Hermetic tests for the shared review-prompt helpers (v1.9 item 2).

Locks the tier prompt/dispatch contract: letter aliases, word forms,
Enter-defaults, the bulk-confirm threshold, skip semantics — and the
load-bearing v1.8 guard: review-only items (author removals) never reach
a bulk apply, and a cancelled bulk skips their review too.
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from rich.console import Console

from calibre_toolkit import review_prompts
from calibre_toolkit.modules.authors import _gate_author_removals
from calibre_toolkit.review_prompts import (
    apply_tier,
    ask_apply_choice,
    bulk_apply_with_review_gate,
)

ENTER = object()  # scripted "just press Enter"


class _ScriptedAsk:
    """Stands in for rich's Prompt.ask: returns scripted answers in order.

    ENTER returns the prompt's default — exactly what pressing Enter does.
    Scripted answers are validated against the prompt's choices so a test
    can't accidentally pass an input the real Prompt would reject.
    """

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[tuple] = []

    def __call__(self, prompt="", *, choices=None, default=None, **kwargs):
        self.calls.append((prompt, choices, default))
        answer = self.answers.pop(0)
        if answer is ENTER:
            return default
        assert choices is None or answer in choices, (
            f"scripted answer {answer!r} not in {choices}"
        )
        return answer


@pytest.fixture
def scripted(monkeypatch):
    def _install(*answers):
        ask = _ScriptedAsk(*answers)
        monkeypatch.setattr(review_prompts.Prompt, "ask", ask)
        return ask
    return _install


def _console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, force_terminal=False, width=200), buf


def _recorder():
    """An apply_batch stub that records what it was given and returns ids."""
    seen: list[list] = []

    def _apply(items):
        seen.append(list(items))
        return [getattr(s, "book_id", i) for i, s in enumerate(items)]

    return _apply, seen


# ── ask_apply_choice ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("answer,expected", [
    ("a", "all"), ("r", "review"), ("s", "skip"),
    ("all", "all"), ("review", "review"), ("skip", "skip"),
])
def test_ask_apply_choice_letters_and_words(scripted, answer, expected):
    ask = scripted(answer)
    console, _ = _console()
    got = ask_apply_choice(console, "Apply?", choices=["all", "review", "skip"], default="all")
    assert got == expected


def test_ask_apply_choice_enter_returns_default(scripted):
    scripted(ENTER)
    console, _ = _console()
    got = ask_apply_choice(console, "Apply?", choices=["all", "review", "skip"], default="review")
    assert got == "review"


def test_ask_apply_choice_four_choice_variant(scripted):
    ask = scripted("h")
    console, _ = _console()
    got = ask_apply_choice(
        console, "Apply changes?",
        choices=["all", "high-only", "review", "skip"], default="review",
    )
    assert got == "high-only"
    _, choices, default = ask.calls[0]
    assert choices == ["all", "high-only", "review", "skip", "a", "h", "r", "s"]
    assert default == "review"


def test_ask_apply_choice_prints_waiting_line(scripted):
    scripted("s")
    console, buf = _console()
    ask_apply_choice(console, "Apply?", choices=["all", "review", "skip"], default="all")
    assert "Waiting for input…" in buf.getvalue()


# ── apply_tier ───────────────────────────────────────────────────────────────

def _tier_kwargs(console, apply_batch, review, **overrides):
    kwargs = dict(
        console=console,
        prompt="Tier?",
        default="all",
        apply_confirm_threshold=20,
        apply_batch=apply_batch,
        review=review,
    )
    kwargs.update(overrides)
    return kwargs


def test_apply_tier_empty_is_silent_noop(scripted):
    ask = scripted()  # no answers available — any prompt would crash
    console, buf = _console()
    applied, declined = apply_tier([], **_tier_kwargs(console, None, None))
    assert (applied, declined) == ([], [])
    assert ask.calls == []
    assert buf.getvalue() == ""


def test_apply_tier_all_below_threshold_applies_without_confirm(scripted):
    ask = scripted("a")
    console, _ = _console()
    apply_batch, seen = _recorder()
    items = [SimpleNamespace(book_id=i) for i in range(3)]
    applied, declined = apply_tier(items, **_tier_kwargs(console, apply_batch, None))
    assert applied == [0, 1, 2]
    assert declined == []
    assert seen == [items]
    assert len(ask.calls) == 1  # tier choice only — no bulk confirm at n=3


def test_apply_tier_all_above_threshold_confirm_yes(scripted):
    ask = scripted("all", "y")
    console, _ = _console()
    apply_batch, seen = _recorder()
    items = [SimpleNamespace(book_id=i) for i in range(25)]
    applied, _ = apply_tier(items, **_tier_kwargs(console, apply_batch, None))
    assert len(applied) == 25
    assert "About to apply to" in ask.calls[1][0]


def test_apply_tier_all_above_threshold_confirm_cancel(scripted):
    scripted("all", "n")
    console, buf = _console()
    apply_batch, seen = _recorder()
    items = [SimpleNamespace(book_id=i) for i in range(25)]
    applied, declined = apply_tier(items, **_tier_kwargs(console, apply_batch, None))
    assert (applied, declined) == ([], [])
    assert seen == []  # nothing bulk-applied after cancel
    assert "Bulk apply cancelled." in buf.getvalue()


def test_apply_tier_review_delegates(scripted):
    scripted("r")
    console, _ = _console()
    reviewed: list[list] = []
    sentinel_declined = [SimpleNamespace(book_id=99)]

    def review(items):
        reviewed.append(list(items))
        return [7], sentinel_declined

    items = [SimpleNamespace(book_id=7)]
    applied, declined = apply_tier(items, **_tier_kwargs(console, None, review))
    assert applied == [7]
    assert declined is sentinel_declined
    assert reviewed == [items]


def test_apply_tier_skip_plain(scripted):
    scripted("s")
    console, buf = _console()
    applied, declined = apply_tier(
        [SimpleNamespace(book_id=1)], **_tier_kwargs(console, None, None),
    )
    assert (applied, declined) == ([], [])
    assert "skipped" not in buf.getvalue()


def test_apply_tier_skip_declines_when_flagged(scripted):
    scripted("skip")
    console, _ = _console()
    items = [SimpleNamespace(book_id=1), SimpleNamespace(book_id=2)]
    applied, declined = apply_tier(
        items, **_tier_kwargs(console, None, None, declined_on_skip=True),
    )
    assert applied == []
    assert declined == items  # same objects, flagged for manual review


def test_apply_tier_skip_message_printed(scripted):
    scripted("s")
    console, buf = _console()
    apply_tier(
        [SimpleNamespace(book_id=1)],
        **_tier_kwargs(console, None, None,
                       skip_message="[dim]1 low-confidence enrichment(s) skipped. Run again to review.[/dim]"),
    )
    assert "skipped. Run again to review." in buf.getvalue()


@pytest.mark.parametrize("default,expect_bulk", [("all", True), ("skip", False)])
def test_apply_tier_enter_takes_tier_default(scripted, default, expect_bulk):
    scripted(ENTER)
    console, _ = _console()
    apply_batch, seen = _recorder()
    items = [SimpleNamespace(book_id=1)]
    applied, declined = apply_tier(
        items,
        **_tier_kwargs(console, apply_batch, None,
                       default=default, declined_on_skip=True),
    )
    if expect_bulk:
        assert seen == [items] and declined == []
    else:
        assert seen == [] and declined == items


# ── bulk_apply_with_review_gate (the v1.8 author-removal guard routing) ──────

def _gated_items(n_bulk=2, n_gated=1, confidence="low"):
    bulk = [SimpleNamespace(book_id=i, removes_author=False, confidence="high")
            for i in range(n_bulk)]
    gated = [SimpleNamespace(book_id=100 + i, removes_author=True, confidence=confidence)
             for i in range(n_gated)]
    return bulk, gated


def test_review_only_items_never_bulk_apply(scripted):
    scripted()  # below threshold: no prompt at all
    console, buf = _console()
    apply_batch, seen = _recorder()
    reviewed: list[list] = []
    bulk, gated = _gated_items()

    applied, declined = bulk_apply_with_review_gate(
        bulk + gated,
        console=console,
        apply_confirm_threshold=20,
        apply_batch=apply_batch,
        review=lambda s: (reviewed.append(list(s)) or [], []),
        is_review_only=lambda s: s.removes_author,
        gate_notice=lambda n: f"{n} author-removal change(s) are never bulk-applied",
    )
    assert seen == [bulk]          # bulk slice only — no gated item, ever
    assert reviewed == [gated]     # gated items routed to per-item review
    assert "1 author-removal change(s) are never bulk-applied" in buf.getvalue()


def test_high_confidence_author_removal_still_review_only(scripted):
    """Confidence does not buy an author removal back into the bulk path."""
    scripted()
    console, _ = _console()
    apply_batch, seen = _recorder()
    reviewed: list[list] = []
    bulk, gated = _gated_items(n_gated=1, confidence="high")

    bulk_apply_with_review_gate(
        bulk + gated,
        console=console,
        apply_confirm_threshold=20,
        apply_batch=apply_batch,
        review=lambda s: (reviewed.append(list(s)) or [], []),
        is_review_only=lambda s: s.removes_author,
    )
    assert all(not s.removes_author for batch in seen for s in batch)
    assert reviewed == [gated]


def test_cancelled_bulk_skips_gated_review(scripted):
    scripted("n")  # bulk over threshold → confirm → cancel
    console, buf = _console()
    apply_batch, seen = _recorder()
    reviewed: list[list] = []
    bulk, gated = _gated_items(n_bulk=25)

    applied, declined = bulk_apply_with_review_gate(
        bulk + gated,
        console=console,
        apply_confirm_threshold=20,
        apply_batch=apply_batch,
        review=lambda s: (reviewed.append(list(s)) or [], []),
        is_review_only=lambda s: s.removes_author,
        cancel_message="[dim]Bulk apply cancelled. No changes applied.[/dim]",
    )
    assert (applied, declined) == ([], [])
    assert seen == []
    assert reviewed == []          # cancel skips the gated review too
    assert "Bulk apply cancelled. No changes applied." in buf.getvalue()


def test_all_gated_goes_straight_to_review(scripted):
    ask = scripted()  # bulk slice empty → no confirm prompt
    console, _ = _console()
    apply_batch, seen = _recorder()
    reviewed: list[list] = []
    _, gated = _gated_items(n_bulk=0, n_gated=2)

    bulk_apply_with_review_gate(
        gated,
        console=console,
        apply_confirm_threshold=20,
        apply_batch=apply_batch,
        review=lambda s: (reviewed.append(list(s)) or [], []),
        is_review_only=lambda s: s.removes_author,
    )
    assert seen == []
    assert reviewed == [gated]
    assert ask.calls == []


def test_detection_plus_routing_chain(scripted):
    """The full v1.8 guard: _gate_author_removals caps a medium-confidence
    removal to low (detection, modules/authors.py), and the gate routing
    keeps it out of the bulk apply regardless."""
    scripted()
    console, _ = _console()
    apply_batch, seen = _recorder()
    reviewed: list[list] = []

    removal = SimpleNamespace(book_id=5, removes_author=True, confidence="medium")
    clean = SimpleNamespace(book_id=6, removes_author=False, confidence="high")

    capped = _gate_author_removals([removal, clean])
    assert capped == 1
    assert removal.confidence == "low"

    bulk_apply_with_review_gate(
        [removal, clean],
        console=console,
        apply_confirm_threshold=20,
        apply_batch=apply_batch,
        review=lambda s: (reviewed.append(list(s)) or [], []),
        is_review_only=lambda s: s.removes_author,
    )
    assert seen == [[clean]]
    assert reviewed == [[removal]]
