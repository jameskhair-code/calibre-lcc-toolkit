"""Unit tests for the audit-log query command (roadmap item 18).

Hermetic — tmpdir audit logs, no live DB/Calibre/AI. Covers the shared
reader, the filters, --since parsing, and the show renderer.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import typer

from calibre_toolkit.commands.audit_log import (
    filter_entries,
    parse_since,
    read_audit_entries,
    run_audit_log_show,
    _parse_ts,
    _preview,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _entry(
    book_id: int,
    field: str = "comments",
    step: str = "comments-enrich",
    confidence: str = "high",
    ts: str = "2026-05-28T12:00:00+00:00",
    new_value: object = "value",
) -> dict:
    return {
        "timestamp": ts,
        "book_id": book_id,
        "field": field,
        "new_value": new_value,
        "confidence": confidence,
        "source": "ai",
        "step": step,
    }


def _write(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


# ── read_audit_entries ───────────────────────────────────────────────────────


def test_read_returns_empty_when_path_missing(tmp_path: Path):
    assert read_audit_entries(tmp_path / "missing.log") == []


def test_read_parses_valid_jsonl_in_file_order(tmp_path: Path):
    p = tmp_path / "audit.log"
    _write(p, [_entry(1), _entry(2), _entry(3)])
    entries = read_audit_entries(p)
    assert [e["book_id"] for e in entries] == [1, 2, 3]


def test_read_skips_malformed_and_non_object_lines(tmp_path: Path):
    p = tmp_path / "audit.log"
    p.write_text(
        json.dumps(_entry(1)) + "\n"
        + "not-json\n"
        + "42\n"             # valid JSON but not an object
        + "\n"              # blank
        + json.dumps(_entry(2)) + "\n",
        encoding="utf-8",
    )
    entries = read_audit_entries(p)
    assert [e["book_id"] for e in entries] == [1, 2]


def test_read_includes_manual_writes_lacking_ai_fields(tmp_path: Path):
    """Unlike calibration's loader, the reader keeps every well-formed line."""
    p = tmp_path / "audit.log"
    manual = {"timestamp": "2026-05-28T12:00:00+00:00", "book_id": 9,
              "field": "#mqg_done", "new_value": True}
    _write(p, [_entry(1), manual])
    entries = read_audit_entries(p)
    assert len(entries) == 2


# ── filter_entries ───────────────────────────────────────────────────────────


def test_filter_none_is_passthrough(tmp_path: Path):
    entries = [_entry(1), _entry(2)]
    assert filter_entries(entries) == entries


def test_filter_by_field_book_step(tmp_path: Path):
    entries = [
        _entry(1, field="comments", step="comments-enrich"),
        _entry(1, field="#lcc", step="lcc-enrich"),
        _entry(2, field="#lcc", step="lcc-enrich"),
    ]
    assert [e["book_id"] for e in filter_entries(entries, field="#lcc")] == [1, 2]
    assert len(filter_entries(entries, book_id=1)) == 2
    assert len(filter_entries(entries, step="lcc-enrich")) == 2
    # AND semantics across filters.
    got = filter_entries(entries, book_id=1, field="#lcc")
    assert len(got) == 1 and got[0]["book_id"] == 1


def test_filter_book_id_handles_bad_values(tmp_path: Path):
    entries = [_entry(1), {"book_id": "oops", "field": "x"}, {"field": "y"}]
    got = filter_entries(entries, book_id=1)
    assert len(got) == 1 and got[0]["book_id"] == 1


def test_filter_since_inclusive_and_drops_unparseable(tmp_path: Path):
    entries = [
        _entry(1, ts="2026-05-27T23:59:59+00:00"),
        _entry(2, ts="2026-05-28T00:00:00+00:00"),   # exactly the cutoff
        _entry(3, ts="2026-05-29T00:00:00+00:00"),
        _entry(4, ts="garbage"),
    ]
    cutoff = datetime(2026, 5, 28, tzinfo=timezone.utc)
    got = filter_entries(entries, since=cutoff)
    assert [e["book_id"] for e in got] == [2, 3]


# ── timestamp / since parsing ────────────────────────────────────────────────


def test_parse_ts_assumes_utc_for_naive():
    dt = _parse_ts("2026-05-28T12:00:00")
    assert dt is not None and dt.tzinfo is not None


def test_parse_ts_returns_none_on_garbage():
    assert _parse_ts("not-a-date") is None
    assert _parse_ts(None) is None


def test_parse_since_date_only_is_midnight_utc():
    dt = parse_since("2026-05-28")
    assert dt == datetime(2026, 5, 28, tzinfo=timezone.utc)


def test_parse_since_rejects_garbage():
    with pytest.raises(typer.BadParameter):
        parse_since("last tuesday")


# ── preview ──────────────────────────────────────────────────────────────────


def test_preview_strips_html_and_joins_lists():
    assert _preview("<p>hi <b>there</b></p>") == "hi there"
    assert _preview(["a", "b", "c"]) == "a, b, c"
    assert _preview(None) == "(no value)"


def test_preview_truncates_long_values():
    out = _preview("x" * 200, max_chars=10)
    assert out.endswith("…") and len(out) <= 11


# ── run_audit_log_show (smoke) ───────────────────────────────────────────────


def test_show_empty_log_does_not_raise(tmp_path: Path):
    run_audit_log_show(tmp_path / "missing.log")


def test_show_renders_with_filters(tmp_path: Path):
    p = tmp_path / "audit.log"
    _write(p, [_entry(1, field="comments"), _entry(2, field="#lcc")])
    run_audit_log_show(p, field="#lcc")


def test_show_limit_keeps_most_recent_window(tmp_path: Path, capsys):
    p = tmp_path / "audit.log"
    _write(p, [_entry(i) for i in range(1, 11)])
    run_audit_log_show(p, limit=3)
    out = capsys.readouterr().out
    # Window is the last 3 of 10 matched; header reflects that.
    assert "showing 3 of 10" in out
