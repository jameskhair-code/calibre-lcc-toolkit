"""
Centralised logging and audit-trail helpers.

The toolkit had no logging infrastructure before v1.1 — diagnosing a bad
batch meant scrolling back through Rich output and hoping the relevant
lines had not already been overwritten. This module provides two layers:

  1. **stdlib logging** with `--verbose` and `--log-file` CLI flags.
     Default is silent (WARNING+ only). `--verbose` raises stderr to DEBUG;
     `--log-file PATH` mirrors all DEBUG-level records to a file.

  2. **Persistent JSONL audit log** at `~/.calibre-toolkit/audit.log`
     (overridable via env var). Every metadata write — applied AI suggestion,
     manual override, MQG completion flag — appends one line:

         {"timestamp": "...", "book_id": 42, "field": "#lcc",
          "new_value": "PR6059", "confidence": "high", "source": "ai"}

     This is the post-hoc "what did this session change?" trail.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# ── Logger setup ────────────────────────────────────────────────────────────

_LOGGER_NAME = "calibre_toolkit"
_DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(
    verbose: bool = False,
    log_file: Path | str | None = None,
) -> logging.Logger:
    """Configure the package logger. Idempotent — repeated calls re-wire handlers.

    - default        → WARNING+ on stderr only
    - verbose        → DEBUG+ on stderr
    - log_file path  → DEBUG+ mirrored to that file (stderr level unchanged)

    Returns the package root logger.
    """
    root = logging.getLogger(_LOGGER_NAME)
    # Wipe any handlers from a previous call to keep behaviour deterministic
    # under repeated CLI invocations within the same Python process (tests, TUI).
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(logging.DEBUG if (verbose or log_file) else logging.WARNING)
    root.propagate = False

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
    stderr_handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    root.addHandler(stderr_handler)

    if log_file:
        path = Path(log_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
        root.addHandler(file_handler)
    return root


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the package root.

    Pass `__name__` from any module — child loggers inherit the handler
    configuration set up in `setup_logging`.
    """
    if name.startswith(_LOGGER_NAME):
        return logging.getLogger(name)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


# ── Audit log ───────────────────────────────────────────────────────────────

# Override via env var for testing or single-host multi-library setups.
_AUDIT_ENV = "CALIBRE_TOOLKIT_AUDIT_LOG"
_DEFAULT_AUDIT_PATH = Path.home() / ".calibre-toolkit" / "audit.log"

# Single global lock guards the append so concurrent callers can't interleave a
# line; one open-append-close per event keeps the file structurally JSONL even
# on crash. The lock is defensive: today every audit_log call happens on the
# main thread (the auditing apply paths — lcc/comments/tags — are sequential
# `for` loops). db.apply_metadata_batch uses a thread pool but does NOT audit;
# if that ever changes, see the regrade-marker note below.
_audit_lock = threading.Lock()


def _audit_path() -> Path:
    override = os.environ.get(_AUDIT_ENV)
    return Path(override).expanduser() if override else _DEFAULT_AUDIT_PATH


# Re-grade marker. When set, every audit_log call within the dynamic scope
# tags its record with `regrade=<marker>` so the write is distinguishable from
# an original AI write — calibration excludes these, and they remain queryable.
# Tagging at the single choke point (audit_log) guarantees no write inside a
# re-grade run escapes the marker.
#
# THREADING CONSTRAINT (load-bearing): a ContextVar is NOT copied into
# ThreadPoolExecutor worker threads. This works only because the auditing apply
# paths (lcc/comments/tags `_apply_batch`) are sequential and call audit_log on
# the same thread that entered `regrade_audit`. If any of those apply loops is
# ever moved onto a thread pool, the marker will silently drop here and re-grade
# writes will pollute calibration — pass the marker explicitly instead.
# `tests/test_regrade.py::test_marker_lands_through_real_apply_paths` drives the
# real apply helpers and will fail if this invariant breaks.
_regrade_marker: ContextVar[str | None] = ContextVar("regrade_marker", default=None)


@contextmanager
def regrade_audit(marker: str) -> Iterator[None]:
    """Within this scope, audit_log tags each record with `regrade=marker`.

    `marker` is the re-grade cutoff (the date the rule changed), recorded so a
    later analysis knows which rule-boundary a re-grade was run against.
    """
    token = _regrade_marker.set(marker)
    try:
        yield
    finally:
        _regrade_marker.reset(token)


def audit_log(
    book_id: int,
    field: str,
    new_value: Any,
    confidence: str = "",
    source: str = "",
    **extra: Any,
) -> None:
    """Append one JSON line to the audit log.

    All metadata-writing code paths should call this just before or after the
    actual write. Failure to write the audit log is logged at WARNING but
    never raised — the user's metadata change always takes precedence over
    audit-trail integrity. Extra kwargs are merged into the record as-is.
    """
    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "book_id": book_id,
        "field": field,
        "new_value": new_value,
    }
    if confidence:
        record["confidence"] = confidence
    if source:
        record["source"] = source
    if extra:
        record.update(extra)

    marker = _regrade_marker.get()
    if marker and "regrade" not in record:
        record["regrade"] = marker

    path = _audit_path()
    try:
        with _audit_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        get_logger(__name__).warning(
            "audit log write failed (%s): %s", path, e,
        )
