"""Shared review-prompt helpers — the single home for the tiered apply flow.

Three seams, composed by the five AI-suggest commands (v1.9 item 2):

- `ask_apply_choice` — the letter-alias apply prompt ([a]ll / [r]eview /
  [s]kip, plus clean-titles' 4-choice variant).
- `bulk_apply_with_review_gate` — the "all" path: the v1.6 bulk-apply
  confirmation gate plus the v1.8 author-removal routing (`is_review_only`
  items are never bulk-applied; a cancelled bulk skips their review too).
- `apply_tier` — one confidence tier's full prompt-and-dispatch block.

Deliberately NOT generalised over tags-review's per-book a/k/e/s/q flow or
clean-identifiers' fix-up flow — those are different shapes, not this tier
pattern. Prompt strings are rendered by the callers (tier colours, nouns,
and counts differ per step); these helpers take the final string.
"""

from __future__ import annotations

from typing import Callable

from rich.console import Console
from rich.prompt import Prompt


def confirm_bulk_apply(n: int, threshold: int, console: Console) -> bool:
    """Confirm a bulk apply when n exceeds threshold.

    Returns True if the apply should proceed, False if the user cancelled.
    Below-threshold batches return True immediately without prompting.
    """
    if n <= threshold:
        return True
    console.print("[dim]Waiting for input…[/dim]")
    return Prompt.ask(
        f"About to apply to [bold]{n}[/bold] books. Proceed?",
        choices=["y", "n"], default="n",
        show_choices=True, show_default=True,
    ) == "y"


def ask_apply_choice(
    console: Console,
    prompt: str,
    *,
    choices: list[str],
    default: str,
) -> str:
    """Ask an apply prompt accepting full words or first-letter aliases.

    Prints the standard waiting line, asks with the full words plus their
    first letters as valid inputs (show_choices=False — the rendered prompt
    text already names the options), and returns the chosen full word.
    Enter returns `default`.
    """
    aliases = {c[0]: c for c in choices}
    console.print("[dim]Waiting for input…[/dim]")
    choice = Prompt.ask(
        prompt,
        choices=list(choices) + list(aliases),
        default=default,
        show_choices=False,
    )
    return aliases.get(choice, choice)


def bulk_apply_with_review_gate(
    items: list,
    *,
    console: Console,
    apply_confirm_threshold: int,
    apply_batch: Callable[[list], list[int]],
    review: Callable[[list], tuple[list[int], list]],
    is_review_only: Callable | None = None,
    gate_notice: Callable[[int], str] | None = None,
    cancel_message: str = "[dim]Bulk apply cancelled.[/dim]",
) -> tuple[list[int], list]:
    """The "all" path: bulk-apply with the review-only gate.

    Items matching `is_review_only` are never bulk-applied — they are routed
    through `review` one by one after `gate_notice` (the v1.8 author-removal
    guard's routing; detection lives with the suggestion type). A cancelled
    bulk confirm skips the gated review too — "all" was cancelled, nothing
    proceeds. With `is_review_only=None` this degenerates to the plain
    confirm-then-apply used by the tier blocks.

    Returns (applied_book_ids, declined_suggestions).
    """
    gated = [s for s in items if is_review_only and is_review_only(s)]
    bulk = [s for s in items if not (is_review_only and is_review_only(s))]
    applied: list[int] = []
    declined: list = []
    if bulk:
        if confirm_bulk_apply(len(bulk), apply_confirm_threshold, console):
            applied += apply_batch(bulk)
        else:
            console.print(cancel_message)
            return applied, declined
    if gated:
        if gate_notice:
            console.print(gate_notice(len(gated)))
        a, d = review(gated)
        applied += a
        declined += d
    return applied, declined


def apply_tier(
    items: list,
    *,
    console: Console,
    prompt: str,
    default: str,
    apply_confirm_threshold: int,
    apply_batch: Callable[[list], list[int]],
    review: Callable[[list], tuple[list[int], list]],
    declined_on_skip: bool = False,
    skip_message: str | None = None,
) -> tuple[list[int], list]:
    """One confidence tier's [a]ll / [r]eview / [s]kip block.

    Empty tiers are a silent no-op. "all" runs the bulk-confirm gate then
    `apply_batch`; "review" delegates to `review` (which returns
    (applied_ids, declined)); "skip" returns the items as declined when
    `declined_on_skip` (the low-tier flag-for-manual behaviour) and prints
    `skip_message` when given.

    Returns (applied_book_ids, declined_suggestions).
    """
    if not items:
        return [], []
    choice = ask_apply_choice(
        console, prompt, choices=["all", "review", "skip"], default=default,
    )
    if choice == "all":
        return bulk_apply_with_review_gate(
            items,
            console=console,
            apply_confirm_threshold=apply_confirm_threshold,
            apply_batch=apply_batch,
            review=review,
        )
    if choice == "review":
        return review(items)
    if skip_message:
        console.print(skip_message)
    return [], (list(items) if declined_on_skip else [])
