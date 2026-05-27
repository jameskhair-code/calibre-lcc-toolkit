"""Shared review-prompt helpers.

Currently houses one function — the bulk-apply confirmation gate added in
v1.6 (item 8). The duplicated per-tier Prompt.ask blocks across the five
AI-suggest modules will fold into this module in v1.9 item 5.
"""

from __future__ import annotations

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
