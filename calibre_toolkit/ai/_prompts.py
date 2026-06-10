"""Rules and prompt-fragment loading shared by every AI step module.

Lives in its own module (rather than _client.py) so the step modules can
import it without creating a cycle — _client.py imports the step modules
for its method glue.
"""

from __future__ import annotations

from pathlib import Path

# Rules file lives alongside the package root
_RULES_DIR = Path(__file__).parent.parent.parent / "rules"
_PROMPTS_DIR = _RULES_DIR / "prompts"


def _load_rules(rules_file: str) -> str:
    path = _RULES_DIR / rules_file
    if not path.exists():
        raise FileNotFoundError(
            f"Rules file not found: {path}\n"
            "Expected rules/ directory alongside the calibre_toolkit package."
        )
    return path.read_text(encoding="utf-8")


def _load_prompt(prompt_file: str) -> str:
    """Load a prompt fragment from rules/prompts/.

    Externalized so that prompt prose can be edited without touching code
    and stays in sync with the rules files it sits beside. See item 10 in
    ROADMAP.md.
    """
    path = _PROMPTS_DIR / prompt_file
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt fragment not found: {path}\n"
            "Expected rules/prompts/ directory alongside the calibre_toolkit package."
        )
    return path.read_text(encoding="utf-8")
