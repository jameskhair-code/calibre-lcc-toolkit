"""
Calibre Toolkit — Terminal UI

Two-panel layout:
  Left  — MQG pipeline steps with live progress bars
  Right — Step detail, description, and action buttons

Selecting a step and pressing Enter (or clicking an action) suspends the
TUI, runs the CLI command in the real terminal (so interactive prompts
work), then returns to the menu and refreshes stats.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Footer, Label, ListItem, ListView, Rule, Static

from ..db import CalibreDB


# ── Step / Action data model ──────────────────────────────────────────────────

@dataclass
class StepAction:
    label: str
    cli_args: list[str]   # args appended after  python -m calibre_toolkit.cli
    description: str = ""


@dataclass
class StepDef:
    key: str
    number: str           # "01", "05a" …
    name: str
    description: str
    mqg_column: Optional[str]   # None → library-wide (no per-book progress)
    actions: list[StepAction]


def _build_steps(cfg: dict) -> list[StepDef]:
    mqg      = cfg.get("mqg", {})
    tags_cfg = cfg.get("tags", {})
    lcc_cfg  = cfg.get("lcc", {})
    com_cfg  = cfg.get("comments", {})

    ta_col  = mqg.get("title_author_column",    "#mqg_title_author")
    id_col  = mqg.get("identifiers_column",     "#mqg_identifiers")
    lcc_col = mqg.get("lcc_column",             "#mqg_lcc")
    com_col = com_cfg.get("mqg_column",         "#mqg_comments")
    rev_col = tags_cfg.get("reviewed_column",   "#tags_reviewed")

    return [
        StepDef(
            key="title_author", number="01", name="Title & Author",
            description=(
                "Clean up author names and titles using AI pattern matching "
                "to ensure consistent, correctly capitalised formatting "
                "across the whole library."
            ),
            mqg_column=ta_col,
            actions=[
                StepAction(
                    "Enrich unprocessed books",
                    ["clean-titles", f"not {ta_col}:true"],
                    f"Runs on books where {ta_col} is not yet set",
                ),
                StepAction(
                    "Re-enrich all books",
                    ["clean-titles", "all"],
                    "Re-processes every book regardless of status",
                ),
                StepAction(
                    "Enrich metadata queue",
                    ["clean-titles", "#metadata_queue:true"],
                    "Runs on books currently in your metadata queue",
                ),
            ],
        ),
        StepDef(
            key="identifiers", number="02", name="Identifiers",
            description=(
                "Find and add external identifiers — ISBN, Goodreads, Amazon — "
                "using Calibre's fetch-ebook-metadata tool with live web lookups."
            ),
            mqg_column=id_col,
            actions=[
                StepAction(
                    "Enrich unprocessed books",
                    ["enrich-identifiers", f"not {id_col}:true"],
                    "Runs live lookup on books not yet processed",
                ),
                StepAction(
                    "Force re-lookup (already-sufficient books)",
                    ["enrich-identifiers", f"not {id_col}:true", "--force-lookup"],
                    "Re-fetches even books already marked sufficient",
                ),
            ],
        ),
        StepDef(
            key="lcc", number="03", name="LCC Classification",
            description=(
                "Assign Library of Congress Classification to each book using AI. "
                "Proposes a call number, primary & secondary class, and a one-sentence "
                "subject summary."
            ),
            mqg_column=lcc_col,
            actions=[
                StepAction(
                    "Enrich unprocessed books",
                    ["lcc-enrich", f"{id_col}:true and not {lcc_col}:true"],
                    "Books with identifiers not yet classified",
                ),
                StepAction(
                    "Dry run (preview, no writes)",
                    ["lcc-enrich", f"{id_col}:true and not {lcc_col}:true", "--dry-run"],
                    "Preview AI proposals without writing anything",
                ),
                StepAction(
                    "Re-enrich all (force)",
                    ["lcc-enrich", f"{id_col}:true", "--force"],
                    "Re-processes all books that have identifiers",
                ),
            ],
        ),
        StepDef(
            key="comments", number="04", name="Comments",
            description=(
                "Generate structured book descriptions — The Book, "
                "Something You Might Not Know, Why Read It — "
                "written in the library's established voice."
            ),
            mqg_column=com_col,
            actions=[
                StepAction(
                    "Enrich unprocessed books",
                    ["comments-enrich", f"{lcc_col}:true and not {com_col}:true"],
                    "Books with LCC not yet described",
                ),
                StepAction(
                    "Dry run (preview, no writes)",
                    ["comments-enrich", f"{lcc_col}:true and not {com_col}:true", "--dry-run"],
                    "Preview generated comments without writing",
                ),
                StepAction(
                    "Tone test (3 voice variants, 1 book)",
                    ["comments-enrich", f"{lcc_col}:true", "--tone-test", "--limit", "1"],
                    "Generate 3 voice variants to calibrate tone",
                ),
            ],
        ),
        StepDef(
            key="tags_cleanup", number="05a", name="Tags Cleanup",
            description=(
                "Normalise tag vocabulary across the entire library — "
                "LCSH chains, BISAC codes, encoding noise, taxonomy variants. "
                "Deterministic scanner first, optional AI semantic pass second."
            ),
            mqg_column=None,  # library-wide — no per-book progress column
            actions=[
                StepAction(
                    "Scanner only — fast, no AI",
                    ["tags-cleanup", "--skip-ai"],
                    "Runs deterministic rules only — instant, free",
                ),
                StepAction(
                    "Full cleanup — scanner + AI",
                    ["tags-cleanup"],
                    "Scanner then AI semantic pass — takes a few minutes",
                ),
                StepAction(
                    "Dry run (scanner only, preview)",
                    ["tags-cleanup", "--skip-ai", "--dry-run"],
                    "Preview scanner changes without writing anything",
                ),
            ],
        ),
        StepDef(
            key="tags_review", number="05b", name="Tags Review",
            description=(
                "Interactive per-book tag review with AI assessment. "
                "For each book the full metadata context is shown — description, "
                "LCC, current tags — and the AI proposes improvements. "
                "You approve, edit, or keep before locking."
            ),
            mqg_column=rev_col,
            actions=[
                StepAction(
                    "Review unprocessed books",
                    ["tags-review"],
                    f"All books where {rev_col} is not yet set",
                ),
                StepAction(
                    "Review metadata queue",
                    ["tags-review", "#metadata_queue:true"],
                    "Books currently in your metadata queue",
                ),
                StepAction(
                    "Review without AI (manual only)",
                    ["tags-review", "--no-ai"],
                    "Shows book metadata; you decide without AI input",
                ),
            ],
        ),
    ]


# ── Progress widget ───────────────────────────────────────────────────────────

class StepItem(Static):
    """A single row in the left-panel step list."""

    DEFAULT_CSS = """
    StepItem {
        height: 4;
        padding: 0 1;
        border-bottom: solid $surface-lighten-2;
    }
    """

    def __init__(self, step: StepDef, done: int, total: int, **kw):
        super().__init__(**kw)
        self._step = step
        self._done = done
        self._total = total

    def render(self) -> str:
        step  = self._step
        done  = self._done
        total = self._total

        # Number badge + name
        num   = f"[bold #7c3aed]{step.number}[/]"
        name  = f"[bold]{step.name}[/]"
        line1 = f" {num}  {name}"

        # Progress bar / label
        if step.mqg_column is None or total == 0:
            line2 = "  [dim]Library-wide[/dim]"
        else:
            pct      = done / total
            bar_w    = 18
            filled   = int(pct * bar_w)
            bar      = "[green]" + "█" * filled + "[/green]" + "[dim]" + "░" * (bar_w - filled) + "[/dim]"
            pct_str  = f"{pct * 100:.0f}%"
            line2    = f"  {bar}  [dim]{done:,}/{total:,}  {pct_str}[/dim]"

        return line1 + "\n" + line2


# ── Main App ──────────────────────────────────────────────────────────────────

class CalibreToolkitApp(App):

    CSS = """
    Screen {
        background: #0d1117;
    }

    #left {
        width: 38;
        background: #161b22;
        border-right: solid #30363d;
    }

    #left-header {
        background: #161b22;
        color: #8b949e;
        padding: 0 1;
        height: 2;
        border-bottom: solid #30363d;
        text-style: bold;
    }

    #step-list {
        background: #161b22;
    }

    #step-list > ListItem {
        background: #161b22;
        padding: 0;
    }

    #step-list > ListItem.--highlight {
        background: #1f2d3d;
    }

    #right {
        background: #0d1117;
        padding: 1 3;
    }

    #r-number {
        color: #7c3aed;
        text-style: bold;
        height: 1;
    }

    #r-name {
        text-style: bold;
        color: #e6edf3;
        height: 2;
    }

    #r-desc {
        color: #8b949e;
        height: auto;
        padding-bottom: 1;
    }

    #r-progress {
        color: #3fb950;
        height: 1;
        padding-bottom: 1;
    }

    #r-actions-label {
        color: #484f58;
        height: 1;
        padding-bottom: 1;
    }

    #r-actions {
        height: auto;
    }

    .action-btn {
        width: 100%;
        margin-bottom: 1;
        background: #21262d;
        color: #c9d1d9;
        border: tall #30363d;
        height: 3;
    }

    .action-btn:hover {
        background: #1f6feb;
        color: #ffffff;
        border: tall #1f6feb;
    }

    .action-btn:focus {
        background: #1f6feb;
        border: tall #388bfd;
    }

    Footer {
        background: #161b22;
        color: #8b949e;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh_stats", "Refresh"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up",   "Up",   show=False),
    ]

    _stats: reactive[dict[str, tuple[int, int]]] = reactive({})
    _total_books: reactive[int] = reactive(0)
    _selected_idx: reactive[int] = reactive(0)
    _btn_counter: int = 0                     # increments each render; avoids duplicate IDs
    _action_map: dict[str, StepAction]        # btn_id → action

    def __init__(
        self,
        cfg: dict,
        db: CalibreDB,
        config_path: Path,
        **kw,
    ):
        super().__init__(**kw)
        self._cfg         = cfg
        self._db          = db
        self._config_path = config_path
        self._steps       = _build_steps(cfg)
        self._lib_name    = Path(cfg.get("library_path", "Library")).name
        self._action_map  = {}

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static(f"[bold]MQG Pipeline[/bold]", id="left-header")
        with Horizontal():
            with Vertical(id="left"):
                yield ListView(
                    *[ListItem(StepItem(s, 0, 0, id=f"item-{s.key}")) for s in self._steps],
                    id="step-list",
                )
            with Vertical(id="right"):
                yield Static("", id="r-number")
                yield Static("", id="r-name")
                yield Static("", id="r-desc")
                yield Static("", id="r-progress")
                yield Rule()
                yield Static("[dim]── Actions ──[/dim]", id="r-actions-label")
                yield ScrollableContainer(id="r-actions")
        yield Footer()

    def on_mount(self) -> None:
        self.title     = self._lib_name
        self.sub_title = "Calibre Toolkit"
        self._load_stats()
        # ListView fires Highlighted automatically on mount, which calls _update_right

    # ── Stats loading ─────────────────────────────────────────────────────────

    @work(thread=True)
    def _load_stats(self) -> None:
        total = self._db.count_books()
        stats: dict[str, tuple[int, int]] = {}
        for step in self._steps:
            if step.mqg_column:
                done = self._db.count_column_true(step.mqg_column)
                stats[step.key] = (done, total)
        self.call_from_thread(self._apply_stats, stats, total)

    def _apply_stats(self, stats: dict, total: int) -> None:
        self._total_books = total
        self._stats = stats
        # Update each StepItem widget
        for step in self._steps:
            done, tot = stats.get(step.key, (0, total))
            widget = self.query_one(f"#item-{step.key}", StepItem)
            widget._done  = done
            widget._total = tot
            widget.refresh()
        # Refresh right panel with updated counts
        self._update_right(self._selected_idx)
        self.sub_title = f"Calibre Toolkit  ·  {total:,} books"

    def action_refresh_stats(self) -> None:
        self._load_stats()

    # ── Navigation ────────────────────────────────────────────────────────────

    @on(ListView.Highlighted)
    def on_list_highlighted(self, event: ListView.Highlighted) -> None:
        idx = event.list_view.index
        if idx is not None:
            self._selected_idx = idx
            self._update_right(idx)

    def action_cursor_down(self) -> None:
        self.query_one("#step-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#step-list", ListView).action_cursor_up()

    # ── Right panel ───────────────────────────────────────────────────────────

    def _update_right(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._steps):
            return
        step = self._steps[idx]
        done, total = self._stats.get(step.key, (0, self._total_books))

        self.query_one("#r-number", Static).update(f"Step {step.number}")
        self.query_one("#r-name",   Static).update(f"[bold]{step.name}[/bold]")
        self.query_one("#r-desc",   Static).update(step.description)

        if step.mqg_column is None:
            progress_text = "[dim]Library-wide operation — no per-book tracking[/dim]"
        elif total == 0:
            progress_text = "[dim]No books found[/dim]"
        else:
            pct = done / total
            bar_w  = 24
            filled = int(pct * bar_w)
            bar    = "[green]" + "█" * filled + "[/green]" + "[dim]" + "░" * (bar_w - filled) + "[/dim]"
            progress_text = f"{bar}  [bold green]{done:,}[/bold green][dim]/{total:,}  ({pct*100:.0f}%)[/dim]"

        self.query_one("#r-progress", Static).update(progress_text)

        # Rebuild action buttons — use a monotonic counter so IDs are always unique
        container = self.query_one("#r-actions", ScrollableContainer)
        container.remove_children()
        self._action_map.clear()
        for action in step.actions:
            self._btn_counter += 1
            btn_id = f"btn-{self._btn_counter}"
            self._action_map[btn_id] = action
            btn = Button(
                f"[bold]{action.label}[/bold]\n[dim]{action.description}[/dim]",
                id=btn_id,
                classes="action-btn",
            )
            container.mount(btn)

    # ── Button press → run command ────────────────────────────────────────────

    @on(Button.Pressed, ".action-btn")
    def on_action_pressed(self, event: Button.Pressed) -> None:
        action = self._action_map.get(event.button.id or "")
        if action:
            self._run_action(action)

    def _run_action(self, action: StepAction) -> None:
        # Insert --config after the subcommand name (first element of cli_args)
        # so Typer routes it to the right command before parsing its options.
        subcommand, *rest = action.cli_args
        cmd = [
            sys.executable, "-m", "calibre_toolkit.cli",
            subcommand, "--config", str(self._config_path),
        ] + rest

        with self.suspend():
            # Print a clear divider so the command output is clearly framed
            print(f"\n{'─' * 72}")
            print(f"  Running: {' '.join(action.cli_args)}")
            print(f"{'─' * 72}\n")
            subprocess.run(cmd)
            print(f"\n{'─' * 72}")
            input("  Press Enter to return to the menu…")

        # Refresh stats after returning
        self._load_stats()


# ── Entry point ───────────────────────────────────────────────────────────────

def main(config_path: Optional[Path] = None) -> None:
    import json

    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config.json"

    if not config_path.exists():
        print(f"Error: config.json not found at {config_path}")
        print("Copy config.example.json to config.json and fill in your values.")
        sys.exit(1)

    cfg = json.loads(config_path.read_text(encoding="utf-8"))

    try:
        db = CalibreDB(
            library_path=cfg["library_path"],
            calibredb_path=cfg.get("calibredb_path", "calibredb"),
        )
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    CalibreToolkitApp(cfg=cfg, db=db, config_path=config_path).run()
