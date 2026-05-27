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
from typing import Optional, Union

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
    prompt_limit: bool = False  # if True, ask for a book count before running


@dataclass
class StepDef:
    key: str
    number: str           # "01", "02" …
    name: str
    description: str
    mqg_column: Optional[str]   # None → library-wide (no per-book progress)
    actions: list[StepAction]


@dataclass
class SectionHeader:
    key: str
    name: str


MenuItem = Union[StepDef, SectionHeader]


def _build_steps(cfg: dict) -> list[MenuItem]:
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
                    "Enrich next N unprocessed",
                    ["clean-titles", f"not {ta_col}:true"],
                    f"Processes the next N books where {ta_col} is not yet set",
                    prompt_limit=True,
                ),
                StepAction(
                    "Enrich all unprocessed",
                    ["clean-titles", f"not {ta_col}:true"],
                    f"Runs on all books where {ta_col} is not yet set",
                ),
                StepAction(
                    "Enrich metadata queue",
                    ["clean-titles", "#metadata_queue:true"],
                    "Runs on books currently in your metadata queue",
                ),
                StepAction(
                    "Re-enrich all books",
                    ["clean-titles", "all"],
                    "Re-processes every book regardless of status",
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
                    "Enrich next N unprocessed",
                    ["enrich-identifiers", f"not {id_col}:true", "--force-lookup"],
                    "Processes the next N books still needing work; re-attempts even partially-filled ones",
                    prompt_limit=True,
                ),
                StepAction(
                    "Enrich all unprocessed",
                    ["enrich-identifiers", f"not {id_col}:true"],
                    "Fast bulk run — skips books that already look sufficient",
                ),
                StepAction(
                    "Enrich metadata queue",
                    ["enrich-identifiers", "#metadata_queue:true", "--force-lookup"],
                    "Runs on your metadata queue; re-attempts even already-touched books",
                ),
            ],
        ),
        StepDef(
            key="lcc", number="03", name="LCC Classification",
            description=(
                "Assign Library of Congress Classification to each book using AI. "
                "Proposes a call number, primary & secondary class, and a one-sentence "
                "subject summary — drawn from the identifiers gathered in step 02."
            ),
            mqg_column=lcc_col,
            actions=[
                StepAction(
                    "Enrich next N unprocessed",
                    ["lcc-enrich", f"{id_col}:true and not {lcc_col}:true"],
                    "Processes the next N books with identifiers not yet classified",
                    prompt_limit=True,
                ),
                StepAction(
                    "Enrich all unprocessed",
                    ["lcc-enrich", f"{id_col}:true and not {lcc_col}:true"],
                    "All books with identifiers not yet classified",
                ),
                StepAction(
                    "Enrich metadata queue",
                    ["lcc-enrich", "#metadata_queue:true", "--force"],
                    "Runs on your metadata queue; re-attempts even already-classified books",
                ),
                StepAction(
                    "Re-enrich all (force)",
                    ["lcc-enrich", f"{id_col}:true", "--force"],
                    "Re-processes every book that has identifiers, overwriting existing LCC",
                ),
            ],
        ),
        StepDef(
            key="comments", number="04", name="Comments",
            description=(
                "Generate structured book descriptions — The Book, "
                "Something You Might Not Know, Why Read It — "
                "written in the library's established voice, informed by "
                "the LCC classification and identifiers from earlier steps."
            ),
            mqg_column=com_col,
            actions=[
                StepAction(
                    "Enrich next N unprocessed",
                    ["comments-enrich", f"{lcc_col}:true and not {com_col}:true"],
                    "Processes the next N books with LCC classification not yet described",
                    prompt_limit=True,
                ),
                StepAction(
                    "Enrich all unprocessed",
                    ["comments-enrich", f"{lcc_col}:true and not {com_col}:true"],
                    "Books with LCC classification not yet described",
                ),
                StepAction(
                    "Enrich metadata queue",
                    ["comments-enrich", "#metadata_queue:true", "--force"],
                    "Runs on your metadata queue; includes books previously flagged manual",
                ),
            ],
        ),
        StepDef(
            key="tags_review", number="05", name="Tags",
            description=(
                "Two workflows. Enrich (bulk): AI proposes a full tag set for "
                "books with no tags yet, grouped into high/medium/low confidence "
                "tiers for bulk approval — matches the LCC and Comments flow. "
                "Review (per-book): one book at a time with full context, "
                "approve/edit/keep before locking. Use Enrich first to seed "
                "tags, Review to curate."
            ),
            mqg_column=rev_col,
            actions=[
                StepAction(
                    "Enrich next N unprocessed",
                    ["tags-enrich", f"{lcc_col}:true and not #mqg_tags:true"],
                    "Bulk AI tagging for the next N books with LCC done but no tags yet",
                    prompt_limit=True,
                ),
                StepAction(
                    "Enrich all unprocessed",
                    ["tags-enrich", f"{lcc_col}:true and not #mqg_tags:true"],
                    "Bulk AI tagging for all books with LCC done but no tags yet",
                ),
                StepAction(
                    "Enrich metadata queue",
                    ["tags-enrich", "#metadata_queue:true"],
                    "Bulk AI tagging across your metadata queue",
                ),
                StepAction(
                    "Review unprocessed books",
                    ["tags-review"],
                    f"Per-book curation for books where {rev_col} is not yet set",
                ),
                StepAction(
                    "Review metadata queue",
                    ["tags-review", "#metadata_queue:true"],
                    "Per-book curation across your metadata queue",
                ),
                StepAction(
                    "Review without AI (manual only)",
                    ["tags-review", "--no-ai"],
                    "Per-book review without AI input",
                ),
            ],
        ),

        # ── Maintenance ───────────────────────────────────────────────────────
        SectionHeader(key="maintenance", name="Maintenance"),

        StepDef(
            key="tags_cleanup", number="", name="Tags Cleanup",
            description=(
                "Normalise tag vocabulary across the entire library — "
                "LCSH chains, BISAC codes, encoding noise, taxonomy variants. "
                "Deterministic scanner first, optional AI semantic pass second. "
                "Library-wide variants apply across the full library; "
                "metadata-queue variants only apply changes to books in the queue."
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
                    "Scanner only — metadata queue",
                    ["tags-cleanup", "--skip-ai", "--search", "#metadata_queue:true"],
                    "Deterministic rules; apply only to books in the metadata queue",
                ),
                StepAction(
                    "Full cleanup — metadata queue",
                    ["tags-cleanup", "--search", "#metadata_queue:true"],
                    "Scanner + AI; apply only to books in the metadata queue",
                ),
            ],
        ),
    ]


# ── List widgets ──────────────────────────────────────────────────────────────

class StepItem(Static):
    """A single step row in the left-panel list."""

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

        num   = f"[bold #7c3aed]{step.number}[/]" if step.number else " "
        name  = f"[bold]{step.name}[/]"
        line1 = f" {num}  {name}" if step.number else f"   {name}"

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


class SectionItem(Static):
    """A section-divider row in the left-panel list."""

    DEFAULT_CSS = """
    SectionItem {
        height: 2;
        padding: 0 1;
        color: #484f58;
        border-bottom: solid $surface-lighten-2;
        border-top: solid #30363d;
    }
    """

    def __init__(self, header: SectionHeader, **kw):
        super().__init__(**kw)
        self._header = header

    def render(self) -> str:
        return f" [dim]── {self._header.name} ──[/dim]"


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

    # Digit/letter jump shortcuts: 1-5 jump to the matching MQG step, m to
    # the Maintenance section header, t to Tags Cleanup. Hidden from the
    # footer to keep it readable; the "01"…"05" badges in the step list
    # are the discoverability hook.
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh_stats", "Refresh"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up",   "Up",   show=False),
        Binding("1", "jump(0)", "Step 1", show=False),
        Binding("2", "jump(1)", "Step 2", show=False),
        Binding("3", "jump(2)", "Step 3", show=False),
        Binding("4", "jump(3)", "Step 4", show=False),
        Binding("5", "jump(4)", "Step 5", show=False),
        Binding("m", "jump(5)", "Maintenance", show=False),
        Binding("t", "jump(6)", "Tags Cleanup", show=False),
    ]

    _stats: reactive[dict[str, tuple[int, int]]] = reactive({})
    _total_books: reactive[int] = reactive(0)
    _selected_idx: reactive[int] = reactive(0)
    _btn_counter: int = 0
    _action_map: dict[str, StepAction]

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
        self._menu        = _build_steps(cfg)
        self._lib_name    = Path(cfg.get("library_path", "Library")).name
        self._action_map  = {}

    def _steps_only(self) -> list[StepDef]:
        return [m for m in self._menu if isinstance(m, StepDef)]

    def _format_pipeline_status(
        self,
        stats: dict[str, tuple[int, int]],
        total: int,
        fully_enriched: int,
    ) -> str:
        """Single-line cross-step pipeline summary for #left-header.

        Format: 'Pipeline: 1✓ 2◐ 3◐ 4○ 5○  ·  N/M books fully enriched'.
        ✓ green = all books done · ◐ yellow = some books done · ○ = none done.
        """
        parts: list[str] = []
        for step in self._steps_only():
            if not step.mqg_column or not step.number:
                continue
            done, tot = stats.get(step.key, (0, total))
            if tot > 0 and done == tot:
                icon = "[green]✓[/green]"
            elif done > 0:
                icon = "[yellow]◐[/yellow]"
            else:
                icon = "○"
            n = step.number.lstrip("0") or "0"
            parts.append(f"{n}{icon}")
        return (
            f"[bold]Pipeline:[/bold] {' '.join(parts)}  ·  "
            f"[bold]{fully_enriched:,}[/bold]/{total:,} books fully enriched"
        )

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        items: list[ListItem] = []
        for item in self._menu:
            if isinstance(item, SectionHeader):
                items.append(ListItem(SectionItem(item, id=f"item-{item.key}")))
            else:
                items.append(ListItem(StepItem(item, 0, 0, id=f"item-{item.key}")))

        yield Static(f"[bold]MQG Pipeline[/bold]", id="left-header")
        with Horizontal():
            with Vertical(id="left"):
                yield ListView(*items, id="step-list")
                # Cumulative token-spend line (item 13). Populated on every
                # _load_stats refresh from the persistent usage.jsonl. Sits
                # below the step list so it doesn't crowd navigation.
                yield Static("", id="left-cost")
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

    # ── Stats loading ─────────────────────────────────────────────────────────

    @work(thread=True)
    def _load_stats(self) -> None:
        total = self._db.count_books()
        stats: dict[str, tuple[int, int]] = {}
        gate_labels: list[str] = []
        for step in self._steps_only():
            if step.mqg_column:
                done = self._db.count_column_true(step.mqg_column)
                stats[step.key] = (done, total)
                # Only the numbered MQG steps gate "fully enriched";
                # maintenance items (no step number) are excluded.
                if step.number:
                    gate_labels.append(step.mqg_column)
        fully_enriched = self._db.count_books_with_all_columns_true(gate_labels)
        # Cumulative cost across every prior session — read from the
        # persisted usage log (item 13). Best-effort; failures yield None
        # and the subtitle just omits the cost suffix.
        from ..usage import replay_usage_log
        usage_aggregate = replay_usage_log()
        cost = usage_aggregate.cost_estimate_usd()
        self.call_from_thread(
            self._apply_stats, stats, total, cost, usage_aggregate.call_count, fully_enriched,
        )

    def _apply_stats(
        self,
        stats: dict,
        total: int,
        cumulative_cost: float | None = None,
        call_count: int = 0,
        fully_enriched: int = 0,
    ) -> None:
        self._total_books = total
        self._stats = stats
        for step in self._steps_only():
            done, tot = stats.get(step.key, (0, total))
            widget = self.query_one(f"#item-{step.key}", StepItem)
            widget._done  = done
            widget._total = tot
            widget.refresh()
        self._update_right(self._selected_idx)
        # Cross-step pipeline summary at the top — carries the
        # whole-library "fully enriched" count the per-step left panel
        # can't show. (v1.6 item 4; the shape rescued from v1.5 item 22.)
        self.query_one("#left-header", Static).update(
            self._format_pipeline_status(stats, total, fully_enriched)
        )
        subtitle = f"Calibre Toolkit  ·  {total:,} books"
        if cumulative_cost is not None and call_count > 0:
            subtitle += f"  ·  ≈ ${cumulative_cost:.2f} spent ({call_count:,} AI calls)"
        self.sub_title = subtitle

        # Visible cost line in the left panel — the subtitle only appears in
        # the terminal title bar, which is easy to miss. This puts the
        # number where the user is actually looking.
        cost_widget = self.query_one("#left-cost", Static)
        if call_count > 0:
            cost_str = (
                f"≈ ${cumulative_cost:.2f}" if cumulative_cost is not None else "n/a"
            )
            cost_widget.update(
                f"[dim]── Spend so far ──[/dim]\n"
                f"[bold]{cost_str}[/bold]  [dim]({call_count:,} AI call{'s' if call_count != 1 else ''})[/dim]"
            )
        else:
            cost_widget.update("")

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

    def action_jump(self, idx: int) -> None:
        step_list = self.query_one("#step-list", ListView)
        if 0 <= idx < len(self._menu):
            step_list.index = idx

    # ── Right panel ───────────────────────────────────────────────────────────

    def _update_right(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._menu):
            return
        item = self._menu[idx]

        container = self.query_one("#r-actions", ScrollableContainer)
        container.remove_children()
        self._action_map.clear()

        if isinstance(item, SectionHeader):
            self.query_one("#r-number", Static).update("")
            self.query_one("#r-name",   Static).update(f"[bold]{item.name}[/bold]")
            self.query_one("#r-desc",   Static).update("")
            self.query_one("#r-progress", Static).update("")
            return

        step = item
        done, total = self._stats.get(step.key, (0, self._total_books))

        self.query_one("#r-number", Static).update(f"Step {step.number}" if step.number else "")
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
        subcommand, *rest = action.cli_args

        with self.suspend():
            limit_args: list[str] = []
            if action.prompt_limit:
                print(f"\n{'─' * 72}")
                while True:
                    raw = input("  How many books to process? ").strip()
                    if raw.isdigit() and int(raw) > 0:
                        limit_args = ["--limit", raw]
                        break
                    print("  Please enter a positive number.")

            cmd = [
                sys.executable, "-m", "calibre_toolkit.cli",
                subcommand, "--config", str(self._config_path),
            ] + rest + limit_args

            print(f"\n{'─' * 72}")
            display_args = action.cli_args + (limit_args if limit_args else [])
            print(f"  Running: {' '.join(display_args)}")
            print(f"{'─' * 72}\n")
            result = subprocess.run(cmd)
            print(f"\n{'─' * 72}")
            if result.returncode != 0:
                print(f"  \033[31m✗ Command exited with code {result.returncode}.\033[0m")
                print(f"  \033[31m  Check the output above for the error.\033[0m")
            else:
                print(f"  \033[32m✓ Done.\033[0m")
            input("  Press Enter to return to the menu…")

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
