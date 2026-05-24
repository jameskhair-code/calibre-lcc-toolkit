"""
Onboarding and health-check helpers for the toolkit.

Three entry points consumed by cli.py:

  • run_doctor()        — read-only validation report
  • run_init()          — interactive config.json wizard
  • run_setup_columns() — idempotent creation of the 14 required custom columns

These commands target a first-run user who has installed the package but has
not yet pointed it at a Calibre library or created the columns the pipeline
expects.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

# ── Required-column registry ────────────────────────────────────────────────
#
# The single source of truth for what a healthy library looks like.  Both
# `doctor` and `setup-columns` read this list. Keep in sync with
# docs/Getting-Started.md Step 3.

ColumnDatatype = Literal["bool", "text", "comments", "enumeration"]


@dataclass(frozen=True)
class RequiredColumn:
    lookup: str               # e.g. "#lcc"
    display_name: str         # human-readable column heading
    datatype: ColumnDatatype  # one of the supported types above
    enum_csv: str = ""        # filename under config/ for enumeration values

    @property
    def label(self) -> str:
        """The lookup name without leading '#'."""
        return self.lookup.lstrip("#")


REQUIRED_COLUMNS: tuple[RequiredColumn, ...] = (
    RequiredColumn("#lcc",                     "LCC Call Number",          "text"),
    RequiredColumn("#lcc_primary_class",       "LCC Primary Class",        "enumeration",
                   enum_csv="lcc-primary-canonical.csv"),
    RequiredColumn("#lcc_secondary_class",     "LCC Secondary Class",      "enumeration",
                   enum_csv="lcc-secondary-canonical.csv"),
    RequiredColumn("#lcc_summary",             "LCC Summary",              "comments"),
    RequiredColumn("#mqg_title_author",        "MQG — Title/Author done",  "bool"),
    RequiredColumn("#mqg_identifiers",         "MQG — Identifiers done",   "bool"),
    RequiredColumn("#mqg_identifiers_manual",  "MQG — Identifiers manual", "bool"),
    RequiredColumn("#mqg_lcc",                 "MQG — LCC done",           "bool"),
    RequiredColumn("#mqg_lcc_manual",          "MQG — LCC manual",         "bool"),
    RequiredColumn("#mqg_comments",            "MQG — Comments done",      "bool"),
    RequiredColumn("#mqg_comments_manual",     "MQG — Comments manual",    "bool"),
    RequiredColumn("#mqg_tags",                "MQG — Tags done",          "bool"),
    RequiredColumn("#mqg_tags_manual",         "MQG — Tags manual",        "bool"),
    RequiredColumn("#tags_reviewed",           "Tags reviewed",            "bool"),
)


# ── Helpers ─────────────────────────────────────────────────────────────────

_CONFIG_DIR = Path(__file__).parent.parent / "config"


def _load_enum_values(csv_name: str) -> list[str]:
    """Read the CanonicalValue column from one of the LCC canonical CSVs."""
    path = _CONFIG_DIR / csv_name
    if not path.exists():
        raise FileNotFoundError(f"Enumeration CSV not found: {path}")
    values: list[str] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            v = (row.get("CanonicalValue") or "").strip()
            if v:
                values.append(v)
    if not values:
        raise RuntimeError(f"No CanonicalValue rows found in {path}")
    return values


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON to *path* via temp file + replace so a crash mid-write
    cannot leave a half-written config behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── Existing-column inspection ──────────────────────────────────────────────


@dataclass
class ExistingColumn:
    label: str
    datatype: str
    is_multiple: bool
    normalized: bool


def _read_existing_columns(library_path: Path) -> dict[str, ExistingColumn]:
    """Return {label: ExistingColumn} for every custom column in the library.

    Reads metadata.db directly — no calibredb subprocess.
    """
    db_path = library_path / "metadata.db"
    if not db_path.exists():
        return {}
    uri = f"file:{db_path}?mode=ro"
    out: dict[str, ExistingColumn] = {}
    with sqlite3.connect(uri, uri=True) as conn:
        for row in conn.execute(
            "SELECT label, datatype, is_multiple, normalized FROM custom_columns"
        ):
            label, datatype, is_multiple, normalized = row
            out[label] = ExistingColumn(
                label=label,
                datatype=datatype or "",
                is_multiple=bool(is_multiple),
                normalized=bool(normalized),
            )
    return out


# ── doctor ──────────────────────────────────────────────────────────────────


@dataclass
class CheckResult:
    name: str
    status: Literal["ok", "warn", "fail"]
    detail: str = ""


def _check_config_parses(config_path: Path) -> tuple[CheckResult, dict | None]:
    if not config_path.exists():
        return (
            CheckResult("config.json exists", "fail",
                        f"{config_path} not found. Run `calibre-toolkit init`."),
            None,
        )
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        return (
            CheckResult("config.json parses", "fail",
                        f"{config_path} is not valid JSON: {e}"),
            None,
        )
    missing = [k for k in ("library_path", "calibredb_path") if not cfg.get(k)]
    if missing:
        return (
            CheckResult("config.json required keys", "fail",
                        f"Missing keys: {', '.join(missing)}"),
            cfg,
        )
    return (CheckResult("config.json parses", "ok", str(config_path)), cfg)


def _check_library_path(cfg: dict) -> CheckResult:
    lib = Path(cfg["library_path"])
    db = lib / "metadata.db"
    if not lib.exists():
        return CheckResult("library_path exists", "fail",
                           f"Directory not found: {lib}")
    if not db.exists():
        return CheckResult("library_path has metadata.db", "fail",
                           f"No metadata.db under {lib}")
    return CheckResult("library_path has metadata.db", "ok", str(db))


def _check_calibredb(cfg: dict) -> CheckResult:
    cmd = [cfg.get("calibredb_path", "calibredb"), "--version"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=15)
    except FileNotFoundError:
        return CheckResult("calibredb is runnable", "fail",
                           f"Executable not found: {cmd[0]}")
    except subprocess.TimeoutExpired:
        return CheckResult("calibredb is runnable", "fail",
                           f"{cmd[0]} --version timed out after 15s")
    if r.returncode != 0:
        return CheckResult("calibredb is runnable", "fail",
                           f"`{cmd[0]} --version` exited {r.returncode}: {r.stderr.strip()}")
    version = (r.stdout.strip().splitlines() or [""])[0]
    return CheckResult("calibredb is runnable", "ok", version)


def _check_api_key(cfg: dict) -> CheckResult:
    ai_cfg = cfg.get("ai", {}) or {}
    api_key = ai_cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY") or ""
    if not api_key:
        return CheckResult("Anthropic API key present", "fail",
                           "No api_key in config.ai and ANTHROPIC_API_KEY is unset")
    # Minimal authenticated call — 1-token response, costs ~nothing.
    try:
        from anthropic import Anthropic, APIStatusError, AuthenticationError
    except ImportError:
        return CheckResult("Anthropic API key authenticates", "warn",
                           "anthropic package not installed; skipping live check")
    model = ai_cfg.get("model") or "claude-sonnet-4-6"
    try:
        client = Anthropic(api_key=api_key, max_retries=0, timeout=15.0)
        client.messages.create(
            model=model,
            max_tokens=1,
            messages=[{"role": "user", "content": "."}],
        )
    except AuthenticationError as e:
        return CheckResult("Anthropic API key authenticates", "fail",
                           f"Authentication rejected: {e}")
    except APIStatusError as e:
        return CheckResult("Anthropic API key authenticates", "warn",
                           f"API returned {e.status_code}; key may still be valid")
    except Exception as e:                       # network, timeout, etc.
        return CheckResult("Anthropic API key authenticates", "warn",
                           f"Could not reach Anthropic: {e}")
    return CheckResult("Anthropic API key authenticates", "ok", f"model={model}")


def _check_columns(cfg: dict) -> list[CheckResult]:
    """Verify every entry in REQUIRED_COLUMNS exists and has the expected datatype."""
    lib = Path(cfg["library_path"])
    existing = _read_existing_columns(lib)
    results: list[CheckResult] = []
    for col in REQUIRED_COLUMNS:
        got = existing.get(col.label)
        if got is None:
            results.append(CheckResult(
                f"column {col.lookup}", "fail",
                f"missing — expected datatype '{col.datatype}'. "
                f"Run `calibre-toolkit setup-columns` to create it.",
            ))
            continue
        if got.datatype != col.datatype:
            results.append(CheckResult(
                f"column {col.lookup}", "fail",
                f"wrong type: expected '{col.datatype}', got '{got.datatype}'",
            ))
            continue
        results.append(CheckResult(f"column {col.lookup}", "ok", col.datatype))
    return results


def run_doctor(config_path: Path, console: Console | None = None) -> int:
    """Run all health checks and print a report. Returns 0 on success, 1 on any failure."""
    console = console or Console()

    console.print(Panel(
        "[bold cyan]Calibre Toolkit — Doctor[/bold cyan]\n"
        "Read-only validation of your config, library, and Anthropic credentials.",
        border_style="cyan",
    ))

    all_results: list[CheckResult] = []

    cfg_result, cfg = _check_config_parses(config_path)
    all_results.append(cfg_result)

    if cfg is not None:
        all_results.append(_check_library_path(cfg))
        # Only attempt deeper checks if the library path resolved
        if all_results[-1].status == "ok":
            all_results.extend(_check_columns(cfg))
        all_results.append(_check_calibredb(cfg))
        all_results.append(_check_api_key(cfg))

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("", width=4)
    table.add_column("Check", overflow="fold")
    table.add_column("Detail", overflow="fold")
    glyph = {"ok": "[green]✓[/green]", "warn": "[yellow]![/yellow]", "fail": "[red]✗[/red]"}
    for r in all_results:
        table.add_row(glyph[r.status], r.name, r.detail)
    console.print(table)

    fails = [r for r in all_results if r.status == "fail"]
    warns = [r for r in all_results if r.status == "warn"]

    console.print()
    if fails:
        console.print(f"[red]{len(fails)} check(s) failed.[/red]"
                      + (f" {len(warns)} warning(s)." if warns else ""))
        return 1
    if warns:
        console.print(f"[yellow]All required checks passed, {len(warns)} warning(s).[/yellow]")
        return 0
    console.print("[green]All checks passed.[/green]")
    return 0


# ── init ────────────────────────────────────────────────────────────────────

_DEFAULT_MODEL = "claude-sonnet-4-6"


def _autodetect_calibredb() -> str:
    """Return the first calibredb on PATH, falling back to the bare name."""
    found = shutil.which("calibredb")
    return found or "calibredb"


def run_init(config_path: Path, console: Console | None = None,
             non_interactive: bool = False) -> int:
    """Interactive wizard that writes a complete config.json.

    Existing configs are not overwritten unless the user confirms.
    """
    console = console or Console()

    if config_path.exists():
        console.print(f"[yellow]A config already exists at {config_path}.[/yellow]")
        if non_interactive or not Confirm.ask("Overwrite?", default=False):
            console.print("Aborted; existing config left in place.")
            return 1

    console.print(Panel(
        "[bold cyan]Calibre Toolkit — init[/bold cyan]\n"
        "Walks through library path, calibredb, and Anthropic API key.",
        border_style="cyan",
    ))

    # 1. Library path
    while True:
        library_path = Prompt.ask("Calibre library path (folder containing metadata.db)")
        library_path = library_path.strip().strip('"').strip("'")
        if (Path(library_path) / "metadata.db").exists():
            break
        console.print(f"[red]No metadata.db under {library_path}.[/red] Try again.")

    # 2. calibredb
    suggested = _autodetect_calibredb()
    calibredb_path = Prompt.ask("calibredb executable", default=suggested)
    ver = subprocess.run([calibredb_path, "--version"], capture_output=True,
                         text=True, encoding="utf-8", errors="replace")
    if ver.returncode != 0:
        console.print(f"[yellow]Warning:[/yellow] `{calibredb_path} --version` failed: "
                      f"{ver.stderr.strip()}")
    else:
        console.print(f"  [green]ok[/green] — {ver.stdout.strip().splitlines()[0]}")

    # 3. Anthropic API key
    api_key = Prompt.ask("Anthropic API key (leave blank to use ANTHROPIC_API_KEY env var)",
                         default="", show_default=False, password=True)
    if api_key:
        try:
            from anthropic import Anthropic, AuthenticationError
            client = Anthropic(api_key=api_key, max_retries=0, timeout=15.0)
            client.messages.create(
                model=_DEFAULT_MODEL,
                max_tokens=1,
                messages=[{"role": "user", "content": "."}],
            )
            console.print("  [green]ok[/green] — API key accepted")
        except AuthenticationError:
            console.print("  [red]rejected[/red] — Anthropic returned 401. Saving anyway.")
        except Exception as e:
            console.print(f"  [yellow]warn[/yellow] — could not verify ({e}). Saving anyway.")

    # 4. Per-step model overrides (single prompt, default applies to all)
    model = Prompt.ask("Default Anthropic model", default=_DEFAULT_MODEL)

    cfg = {
        "library_path": library_path,
        "calibredb_path": calibredb_path,
        "ai": {
            "api_key": api_key,
            "model": model,
            "title_author": {"model": model},
            "lcc": {"model": model},
            "comments": {"model": model},
            "tags": {"model": model},
        },
        "identifiers": {
            "fetch_ebook_metadata_path": "",
            "lookup_timeout_seconds": 45,
            "sufficient_types": ["isbn"],
            "mqg_complete_requires": ["grrating", "grvotes"],
        },
        "lcc": {
            "lcc_column": "#lcc",
            "primary_class_column": "#lcc_primary_class",
            "secondary_class_column": "#lcc_secondary_class",
            "lcc_summary_column": "#lcc_summary",
        },
        "comments": {
            "mqg_column": "#mqg_comments",
            "mqg_manual_column": "#mqg_comments_manual",
            "lcc_summary_column": "#lcc_summary",
        },
        "tags": {
            "reviewed_column": "#tags_reviewed",
            "mqg_column": "#mqg_tags",
            "mqg_manual_column": "#mqg_tags_manual",
        },
        "mqg": {
            "title_author_column": "#mqg_title_author",
            "identifiers_column": "#mqg_identifiers",
            "identifiers_manual_column": "#mqg_identifiers_manual",
            "lcc_column": "#mqg_lcc",
            "lcc_manual_column": "#mqg_lcc_manual",
        },
    }
    _atomic_write_json(config_path, cfg)
    console.print(f"\n[green]Wrote config to {config_path}.[/green]")
    console.print("Next: run [bold]calibre-toolkit setup-columns[/bold] to create the "
                  "custom columns, then [bold]calibre-toolkit doctor[/bold] to verify.")
    return 0


# ── setup-columns ───────────────────────────────────────────────────────────


def _calibredb_add_column(calibredb_path: str, library_path: Path,
                          col: RequiredColumn) -> tuple[bool, str]:
    """Invoke `calibredb add_custom_column`. Returns (success, message).

    On enumeration columns the enum values are passed via --display JSON.
    """
    cmd = [
        calibredb_path,
        "add_custom_column",
        "--library-path", str(library_path),
    ]
    if col.datatype == "enumeration":
        values = _load_enum_values(col.enum_csv)
        display = json.dumps({"enum_values": values, "enum_colors": []})
        cmd += ["--display", display]
    cmd += [col.label, col.display_name, col.datatype]

    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return False, (r.stderr.strip() or r.stdout.strip()
                       or f"exit code {r.returncode}")
    return True, r.stdout.strip()


def run_setup_columns(config_path: Path, console: Console | None = None) -> int:
    """Create any missing required custom columns. Idempotent."""
    console = console or Console()

    cfg_result, cfg = _check_config_parses(config_path)
    if cfg is None:
        console.print(f"[red]{cfg_result.detail}[/red]")
        return 1
    lib_check = _check_library_path(cfg)
    if lib_check.status != "ok":
        console.print(f"[red]{lib_check.detail}[/red]")
        return 1

    library_path = Path(cfg["library_path"])
    calibredb_path = cfg.get("calibredb_path", "calibredb")
    existing = _read_existing_columns(library_path)

    console.print(Panel(
        "[bold cyan]Calibre Toolkit — setup-columns[/bold cyan]\n"
        f"Library: {library_path}\n"
        "Calibre must be closed; calibredb cannot write while the GUI is running.",
        border_style="cyan",
    ))

    created: list[str] = []
    skipped: list[str] = []
    mismatched: list[tuple[str, str, str]] = []   # (lookup, expected, got)
    failed: list[tuple[str, str]] = []

    for col in REQUIRED_COLUMNS:
        existing_col = existing.get(col.label)
        if existing_col is not None:
            if existing_col.datatype == col.datatype:
                skipped.append(col.lookup)
            else:
                mismatched.append((col.lookup, col.datatype, existing_col.datatype))
            continue

        console.print(f"  creating [bold]{col.lookup}[/bold] ({col.datatype})…", end="")
        ok, msg = _calibredb_add_column(calibredb_path, library_path, col)
        if ok:
            console.print(" [green]done[/green]")
            created.append(col.lookup)
        else:
            console.print(f" [red]failed[/red]: {msg}")
            failed.append((col.lookup, msg))

    console.print()
    console.print(f"  created:    [green]{len(created)}[/green]")
    console.print(f"  already ok: [dim]{len(skipped)}[/dim]")
    if mismatched:
        console.print(f"  [yellow]wrong type:[/yellow] {len(mismatched)}")
        for lookup, expected, got in mismatched:
            console.print(f"    {lookup}: expected {expected}, got {got} "
                          "— fix manually in Calibre")
    if failed:
        console.print(f"  [red]failed:[/red] {len(failed)}")
        for lookup, msg in failed:
            console.print(f"    {lookup}: {msg}")
        return 1
    if mismatched:
        return 1
    return 0
