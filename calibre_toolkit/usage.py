"""
Token usage + cost telemetry for Anthropic API calls.

Each call to ai.AIClient._call captures the `usage` block from the
Anthropic response, which carries four counts:

  - input_tokens                 — uncached input
  - output_tokens                — model output
  - cache_creation_input_tokens  — tokens written to the prompt cache
  - cache_read_input_tokens      — tokens served from the prompt cache

The last two matter for cost: cache reads are ~10x cheaper than fresh
input on Sonnet/Opus, and the system prompt block in ai.py is marked
with `cache_control: ephemeral` specifically so that successive batches
in the same run pay near-zero for the (large) rules file. Item 13
exists in part to *measure* that claim — see ai.py:4–7 for the
original wording.

This module is read-only with respect to behaviour: it only observes.
A failure to write the usage log is logged at WARNING but never raised
— a metadata batch must never fail because telemetry couldn't be
persisted.

See ROADMAP.md item 13.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .logging_config import get_logger

_log = get_logger(__name__)


# ── Token counts ─────────────────────────────────────────────────────────────


@dataclass
class TokenUsage:
    """One call's worth of Anthropic token counts."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        if not isinstance(other, TokenUsage):
            return NotImplemented
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_input_tokens=(
                self.cache_creation_input_tokens + other.cache_creation_input_tokens
            ),
            cache_read_input_tokens=(
                self.cache_read_input_tokens + other.cache_read_input_tokens
            ),
        )

    @property
    def total_input(self) -> int:
        """Every input-side token billed in any tier."""
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    @property
    def cache_hit_rate(self) -> float | None:
        """Fraction of input-side tokens served from the prompt cache.

        Returns None when the total is zero (no calls made). 1.0 means
        every input token came from cache; 0.0 means none did. This is
        the metric that validates the prompt-caching claim in ai.py.
        """
        if self.total_input == 0:
            return None
        return self.cache_read_input_tokens / self.total_input


def parse_usage(raw_usage: Any) -> TokenUsage:
    """Extract a TokenUsage from an Anthropic response's `usage` attribute.

    The Anthropic SDK exposes `usage` as a Pydantic model on success but
    we accept dicts too so test fixtures stay readable.
    """
    if raw_usage is None:
        return TokenUsage()

    def _get(name: str) -> int:
        if isinstance(raw_usage, dict):
            value = raw_usage.get(name)
        else:
            value = getattr(raw_usage, name, None)
        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    return TokenUsage(
        input_tokens=_get("input_tokens"),
        output_tokens=_get("output_tokens"),
        cache_creation_input_tokens=_get("cache_creation_input_tokens"),
        cache_read_input_tokens=_get("cache_read_input_tokens"),
    )


# ── Pricing ──────────────────────────────────────────────────────────────────
#
# USD per million tokens. Anthropic's public list prices as of January 2026
# for the Claude 4.x family. Sources: anthropic.com/pricing. Keyed by model
# family prefix so a new minor version (claude-sonnet-4-7, 4-8) inherits
# pricing until a deliberate update.
#
# When the model is unknown we return None and the summary omits the
# dollar estimate — token counts are still shown so the user can plug
# them into a calculator manually.

@dataclass(frozen=True)
class _PriceTable:
    input_per_million: float
    output_per_million: float
    cache_read_per_million: float
    cache_write_per_million: float


_PRICES: dict[str, _PriceTable] = {
    "claude-opus-4": _PriceTable(
        input_per_million=15.00,
        output_per_million=75.00,
        cache_read_per_million=1.50,
        cache_write_per_million=18.75,
    ),
    "claude-sonnet-4": _PriceTable(
        input_per_million=3.00,
        output_per_million=15.00,
        cache_read_per_million=0.30,
        cache_write_per_million=3.75,
    ),
    "claude-haiku-4": _PriceTable(
        input_per_million=0.80,
        output_per_million=4.00,
        cache_read_per_million=0.08,
        cache_write_per_million=1.00,
    ),
    # 3.x legacy support — older but still callable.
    "claude-3-5-sonnet": _PriceTable(
        input_per_million=3.00,
        output_per_million=15.00,
        cache_read_per_million=0.30,
        cache_write_per_million=3.75,
    ),
    "claude-3-5-haiku": _PriceTable(
        input_per_million=0.80,
        output_per_million=4.00,
        cache_read_per_million=0.08,
        cache_write_per_million=1.00,
    ),
}


def _resolve_price_table(model: str) -> _PriceTable | None:
    """Pick the price table by longest matching family prefix."""
    if not model:
        return None
    matches = [k for k in _PRICES if model.startswith(k)]
    if not matches:
        return None
    longest = max(matches, key=len)
    return _PRICES[longest]


def cost_estimate_usd(usage: TokenUsage, model: str) -> float | None:
    """Approximate USD cost of one call. None when the model is unpriced."""
    price = _resolve_price_table(model)
    if price is None:
        return None
    return (
        usage.input_tokens               * price.input_per_million        / 1_000_000
        + usage.output_tokens            * price.output_per_million       / 1_000_000
        + usage.cache_read_input_tokens  * price.cache_read_per_million   / 1_000_000
        + usage.cache_creation_input_tokens * price.cache_write_per_million / 1_000_000
    )


# ── Aggregate ────────────────────────────────────────────────────────────────


@dataclass
class UsageAggregate:
    """Running totals attached to one AIClient instance.

    Threadsafe — multiple concurrent batches accumulate into the same
    aggregate. The lock guards the dataclass mutations; reads of the
    plain attributes are atomic enough for periodic printing.
    """
    total: TokenUsage = field(default_factory=TokenUsage)
    call_count: int = 0
    by_model: dict[str, TokenUsage] = field(default_factory=dict)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False,
    )

    def record(self, usage: TokenUsage, model: str) -> None:
        with self._lock:
            self.total = self.total + usage
            self.call_count += 1
            self.by_model[model] = self.by_model.get(model, TokenUsage()) + usage

    def cost_estimate_usd(self) -> float | None:
        """Sum the per-model cost estimates. Returns None only when every
        model in the aggregate is unpriced; partial pricing still produces
        a (possibly under-counted) estimate."""
        any_priced = False
        total = 0.0
        for model, u in self.by_model.items():
            c = cost_estimate_usd(u, model)
            if c is not None:
                any_priced = True
                total += c
        return total if any_priced else None


# ── Pretty-print summary ─────────────────────────────────────────────────────


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def format_summary(aggregate: UsageAggregate, step_label: str = "") -> str:
    """One-line-ish human summary for end-of-step display.

    Example output:
      Tokens used: 45,230 input + 12,104 output  (cache: 38,991 read /
      4,200 write — 86.2% hit rate)  ≈ $0.47  · 12 API call(s)
    """
    total = aggregate.total
    if aggregate.call_count == 0:
        return f"Tokens used: 0 (no AI calls)"

    parts: list[str] = []
    if step_label:
        parts.append(f"[bold]{step_label}[/bold] · ")

    parts.append(
        f"Tokens used: {_fmt_int(total.input_tokens)} input + "
        f"{_fmt_int(total.output_tokens)} output"
    )

    cache_used = (
        total.cache_creation_input_tokens > 0
        or total.cache_read_input_tokens > 0
    )
    if cache_used:
        hit_rate = total.cache_hit_rate
        hit_rate_str = (
            f"{hit_rate * 100:.1f}% hit rate" if hit_rate is not None else "n/a"
        )
        parts.append(
            f"  (cache: {_fmt_int(total.cache_read_input_tokens)} read / "
            f"{_fmt_int(total.cache_creation_input_tokens)} write — {hit_rate_str})"
        )

    cost = aggregate.cost_estimate_usd()
    if cost is not None:
        parts.append(f"  ≈ ${cost:.2f}")

    parts.append(f"  · {aggregate.call_count} API call(s)")
    return "".join(parts)


# ── Persistent usage log ─────────────────────────────────────────────────────
#
# Mirrors the audit log pattern in logging_config.py. Per-call JSONL events
# at ~/.calibre-toolkit/usage.jsonl. The TUI's overview panel and any
# future cost dashboard can replay this log to reconstruct cumulative
# spend without touching the live AIClient.

_USAGE_ENV = "CALIBRE_TOOLKIT_USAGE_LOG"
_DEFAULT_USAGE_PATH = Path.home() / ".calibre-toolkit" / "usage.jsonl"

_usage_lock = threading.Lock()


def _usage_path() -> Path:
    override = os.environ.get(_USAGE_ENV)
    return Path(override).expanduser() if override else _DEFAULT_USAGE_PATH


def log_usage(usage: TokenUsage, model: str, step: str = "") -> None:
    """Append one usage event to the persistent log.

    Best-effort: filesystem errors are logged at WARNING and swallowed.
    A telemetry write failing must never break a metadata batch.
    """
    cost = cost_estimate_usd(usage, model)
    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "step": step,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_creation_input_tokens": usage.cache_creation_input_tokens,
        "cache_read_input_tokens": usage.cache_read_input_tokens,
    }
    if cost is not None:
        record["estimated_cost_usd"] = round(cost, 6)

    path = _usage_path()
    try:
        with _usage_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        _log.warning("usage log write failed (%s): %s", path, e)


def replay_usage_log(path: Path | None = None) -> UsageAggregate:
    """Reconstruct an aggregate from the on-disk JSONL log.

    Used by the TUI to display cumulative cost across all sessions.
    Unparseable lines are skipped — corrupted writes from a crash
    should not prevent valid history from being read.
    """
    aggregate = UsageAggregate()
    p = path or _usage_path()
    if not p.exists():
        return aggregate
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                usage = TokenUsage(
                    input_tokens=int(record.get("input_tokens", 0) or 0),
                    output_tokens=int(record.get("output_tokens", 0) or 0),
                    cache_creation_input_tokens=int(
                        record.get("cache_creation_input_tokens", 0) or 0
                    ),
                    cache_read_input_tokens=int(
                        record.get("cache_read_input_tokens", 0) or 0
                    ),
                )
                model = str(record.get("model", "") or "")
                aggregate.record(usage, model)
    except OSError as e:
        _log.warning("usage log read failed (%s): %s", p, e)
    return aggregate
